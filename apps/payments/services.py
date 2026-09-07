"""
Payment business rules.  OWNER: Dev 3 — Customer Finance

- Every payment is a separate immutable record. Never edit an amount.
- Reject amount > remaining invoice balance (BUSINESS_RULE_VIOLATION).
- On a COMPLETED payment: auto-create a Receipt, recompute invoice rollups,
  update booking.payment_status, and mark the booking COMPLETED when paid in full.
- Void (COMPLETED -> VOIDED) corrects a mistake; it is NOT a refund.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.invoices.services import InvoiceService
from apps.notifications.constants import NotificationType
from apps.notifications.services import FINANCE_NOTIFY_ROLES, safe_notify_roles
from apps.payments.repositories import PaymentRepository
from apps.receipts.repositories import ReceiptRepository
from core.constants import BookingStatus, Collections, InvoiceStatus, PaymentMethod, PaymentRecordStatus, PaymentStatus
from core.database import get_collection
from core.exceptions import BusinessRuleViolation, NotFoundError, ValidationError
from core.money import ZERO, to_decimal, to_decimal128, to_money
from core.numbering import next_number
from core.soft_delete import stamp_new
from core.utils import parse_object_id, serialize_id, utcnow

VALID_METHODS = {m.value for m in PaymentMethod}


def present_payment(doc: dict) -> dict:
    if not doc:
        return {}
    return {
        "id": serialize_id(doc.get("_id")),
        "payment_number": doc.get("payment_number"),
        "invoice_id": serialize_id(doc.get("invoice_id")),
        "booking_id": serialize_id(doc.get("booking_id")),
        "customer_id": serialize_id(doc.get("customer_id")),
        "amount": str(to_money(doc.get("amount", 0))),
        "currency": doc.get("currency"),
        "payment_method": doc.get("payment_method"),
        "payment_date": doc.get("payment_date"),
        "reference_number": doc.get("reference_number"),
        "status": doc.get("status"),
    }


class PaymentService:
    def __init__(self, repository: PaymentRepository | None = None):
        self.repository = repository or PaymentRepository()
        self.invoices = InvoiceService()

    def list_items(self, **filters) -> list[dict]:
        return [present_payment(d) for d in self.repository.list_payments(**filters)]

    def get(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Payment not found.")
        return present_payment(doc)

    def for_invoice(self, invoice_id: str) -> list[dict]:
        return [present_payment(d) for d in self.repository.find_for_invoice(invoice_id)]

    def find_for_booking(self, booking_id) -> list[dict]:
        return [present_payment(d) for d in self.repository.find_for_booking(booking_id)]

    # ---- record a payment against an invoice (the main path) ---------------
    def record_for_invoice(self, invoice_id: str, *, amount, method: str,
                           recorded_by: str, reference_number: str | None = None,
                           notes: str | None = None) -> dict:
        invoice = self.invoices._get_raw(invoice_id)
        if invoice.get("status") in {
            InvoiceStatus.CANCELLED.value,
            InvoiceStatus.REFUNDED.value,
        }:
            raise BusinessRuleViolation("Cannot record a payment against a cancelled or refunded invoice.")
        if invoice.get("booking_id"):
            booking = get_collection(Collections.BOOKINGS).find_one({
                "_id": invoice["booking_id"],
                "is_deleted": {"$ne": True},
            })
            if booking and booking.get("booking_status") == BookingStatus.CANCELLED.value:
                raise BusinessRuleViolation("Cannot record a payment for a cancelled booking.")

        amount_dec = to_money(amount)
        if amount_dec <= ZERO:
            raise ValidationError("Payment amount must be positive.")
        if method not in VALID_METHODS:
            raise ValidationError(f"Invalid payment method. Allowed: {sorted(VALID_METHODS)}.")

        reference = (reference_number or "").strip() or None
        if reference:
            existing = self.repository.find_completed_by_reference(invoice["_id"], reference)
            if existing:
                return present_payment(existing)
        else:
            duplicate = self.repository.find_recent_duplicate(
                invoice["_id"],
                amount=amount_dec,
                method=method,
                recorded_by=recorded_by,
                since=utcnow() - timedelta(seconds=45),
            )
            if duplicate:
                return present_payment(duplicate)

        reserved = self.invoices.repository.try_consume_remaining(invoice["_id"], amount_dec)
        if not reserved:
            remaining = self.invoices.money_snapshot(invoice_id)["remaining"]
            raise BusinessRuleViolation(
                f"Payment {amount_dec} exceeds remaining balance {to_money(remaining)}."
            )

        now = utcnow()
        doc = stamp_new({
            "payment_number": next_number(Collections.PAYMENTS),
            "invoice_id": invoice["_id"],
            "booking_id": invoice.get("booking_id"),
            "customer_id": invoice.get("customer_id"),
            "amount": to_decimal128(amount_dec),
            "currency": invoice.get("currency", "USD"),
            "payment_method": method,
            "payment_date": now,
            "reference_number": reference,
            "status": PaymentRecordStatus.COMPLETED.value,
            "refundable_remaining": to_decimal128(amount_dec),
            "notes": notes,
            "recorded_by": parse_object_id(recorded_by, field="recorded_by"),
            "created_at": now,
        })
        try:
            result = self.repository.insert(doc)
        except Exception:
            self.invoices.recompute_rollups(invoice_id)
            raise
        doc["_id"] = result.inserted_id

        # Side effects of a COMPLETED payment:
        self._issue_receipt(doc)
        self.invoices.recompute_rollups(invoice_id)
        _sync_booking_payment_status(invoice.get("booking_id"))
        presented = present_payment(doc)
        safe_audit(
            actor_id=recorded_by,
            action=AuditAction.CREATED.value,
            entity_type="payments",
            entity_id=doc["_id"],
            description=f"Recorded payment {presented.get('payment_number')}.",
            after={"payment_number": presented.get("payment_number"), "amount": presented.get("amount")},
        )
        safe_notify_roles(
            FINANCE_NOTIFY_ROLES,
            type=NotificationType.PAYMENT.value,
            title=f"Payment {presented.get('payment_number')}",
            message=f"A customer payment of {presented.get('amount')} was recorded.",
            related_entity_type="payments",
            related_entity_id=doc["_id"],
            exclude_user_id=recorded_by,
        )
        return presented

    def void(self, payment_id: str, *, actor_id: str) -> dict:
        doc = self.repository.find_by_id(payment_id)
        if not doc:
            raise NotFoundError("Payment not found.")
        if doc.get("status") == PaymentRecordStatus.VOIDED.value:
            raise BusinessRuleViolation("Payment is already voided.")
        refund = get_collection(Collections.REFUNDS).find_one(
            {
                "payment_id": doc["_id"],
                "status": {"$in": ["PENDING", "APPROVED", "COMPLETED"]},
                "is_deleted": {"$ne": True},
            }
        )
        if refund:
            raise BusinessRuleViolation("This payment has refunds. Reject or complete them before voiding.")
        self.repository.mark_voided(payment_id)
        # Voided money no longer counts — recompute the invoice + booking.
        self.invoices.recompute_rollups(serialize_id(doc["invoice_id"]))
        _sync_booking_payment_status(doc.get("booking_id"))
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.VOIDED.value,
            entity_type="payments",
            entity_id=doc["_id"],
            description=f"Voided payment {doc.get('payment_number')}.",
        )
        return self.get(payment_id)

    # ---- receipt auto-issue (no public POST for receipts) ------------------
    def _issue_receipt(self, payment: dict) -> None:
        receipts = ReceiptRepository()
        if receipts.find_by_payment(payment["_id"]):
            return
        receipts.insert(stamp_new({
            "receipt_number": next_number(Collections.RECEIPTS),
            "payment_id": payment["_id"],
            "invoice_id": payment.get("invoice_id"),
            "customer_id": payment.get("customer_id"),
            "amount": payment.get("amount"),
            "payment_method": payment.get("payment_method"),
            "issued_at": utcnow(),
            "issued_by": payment.get("recorded_by"),
        }))


def _sync_booking_payment_status(booking_id) -> None:
    """
    Recompute booking.payment_status from the invoice rollups + refunds.
    A confirmed booking becomes COMPLETED when the invoice is paid in full,
    and returns to CONFIRMED if that paid-in-full state is later undone.
    """
    if not booking_id:
        return
    invoices = get_collection(Collections.INVOICES)
    invoice = invoices.find_one({"booking_id": booking_id, "is_deleted": {"$ne": True}})
    if not invoice:
        return
    total = to_decimal(invoice.get("total_amount", 0))
    paid = to_decimal(invoice.get("paid_amount", 0))
    refunded = to_decimal(invoice.get("refunded_amount", 0))

    if refunded > ZERO:
        status = "REFUNDED" if refunded >= paid and paid > ZERO else "PARTIALLY_REFUNDED"
    elif paid <= ZERO:
        status = "UNPAID"
    elif paid < total:
        status = "PARTIALLY_PAID"
    else:
        status = "PAID"

    bookings = get_collection(Collections.BOOKINGS)
    booking = bookings.find_one({"_id": booking_id, "is_deleted": {"$ne": True}})
    if not booking:
        return
    updates = {"payment_status": status, "updated_at": utcnow()}
    booking_status = booking.get("booking_status")
    if booking_status == BookingStatus.CONFIRMED.value and status == PaymentStatus.PAID.value:
        updates["booking_status"] = BookingStatus.COMPLETED.value
    elif booking_status == BookingStatus.COMPLETED.value and status != PaymentStatus.PAID.value:
        updates["booking_status"] = BookingStatus.CONFIRMED.value
    bookings.update_one({"_id": booking_id, "is_deleted": {"$ne": True}}, {"$set": updates})
