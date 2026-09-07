"""
Invoice business rules.  OWNER: Dev 3 — Customer Finance

Rules enforced here:
- Only a CONFIRMED or COMPLETED booking can be invoiced.
- One live invoice per booking (a second create returns the existing invoice).
- taxable_amount = subtotal - discount.amount ; total = taxable + tax.amount
- Status is DERIVED from paid/refunded amounts, never set to PAID by hand.
- CANCELLED invoices keep that status even if rollups are recomputed.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.bookings.repositories import BookingRepository
from apps.invoices.repositories import InvoiceRepository
from apps.notifications.constants import NotificationType
from apps.notifications.services import FINANCE_NOTIFY_ROLES, safe_notify_roles
from core.constants import BookingStatus, Collections, DEFAULT_CURRENCY, InvoiceStatus
from core.database import get_collection
from core.exceptions import BusinessRuleViolation, NotFoundError, ValidationError
from core.money import ZERO, to_decimal, to_decimal128, to_money
from core.numbering import next_number
from core.soft_delete import stamp_new
from core.utils import parse_object_id, serialize_id, utcnow


def remaining_due(total: Decimal, paid: Decimal) -> Decimal:
    """Amount still collectable from the customer. Refunds never reopen AR."""
    leftover = to_money(total - paid)
    return leftover if leftover > ZERO else ZERO


def compute_status(total: Decimal, paid: Decimal, refunded: Decimal) -> str:
    """Derive invoice status from money only. Never set PAID manually."""
    due = remaining_due(total, paid)
    if refunded > ZERO and due <= ZERO:
        if paid > ZERO and refunded >= paid:
            return InvoiceStatus.REFUNDED.value
        return InvoiceStatus.PARTIALLY_REFUNDED.value
    if paid <= ZERO:
        return InvoiceStatus.ISSUED.value
    if due > ZERO:
        return InvoiceStatus.PARTIALLY_PAID.value
    return InvoiceStatus.PAID.value


def _agency_settings() -> dict:
    try:
        from apps.accounts.settings_service import SettingsService

        return SettingsService().get() or {}
    except Exception:
        return {}


def _invoice_due_days(requested: int | None) -> int:
    if requested is not None:
        try:
            days = int(requested)
        except (TypeError, ValueError):
            days = 14
        return max(1, min(days, 120))
    try:
        days = int(_agency_settings().get("invoice_due_days") or 14)
    except (TypeError, ValueError):
        days = 14
    return max(1, min(days, 120))


def _tax_from_settings(pricing: dict, taxable: Decimal) -> tuple[str, Decimal, Decimal]:
    booking_tax = to_decimal(pricing.get("tax_amount", 0))
    booking_rate = to_decimal(pricing.get("tax_rate", 0))
    if booking_tax > ZERO or booking_rate > ZERO:
        name = (pricing.get("tax_name") or "VAT")
        return name, booking_rate, to_money(booking_tax if booking_tax > ZERO else taxable * booking_rate / Decimal("100"))
    settings = _agency_settings()
    if not settings.get("tax_enabled", True):
        return settings.get("tax_name") or "VAT", ZERO, ZERO
    rate = to_money(settings.get("tax_rate") or ZERO)
    name = settings.get("tax_name") or "VAT"
    if rate <= ZERO:
        return name, ZERO, ZERO
    return name, rate, to_money(taxable * rate / Decimal("100"))


def _full_name(customer: dict) -> str:
    """Build a display name from a customer document."""
    first = (customer.get("first_name") or "").strip()
    last = (customer.get("last_name") or "").strip()
    return (first + " " + last).strip() or None


def present_invoice(doc: dict) -> dict:
    """Convert a raw Mongo invoice into a JSON-safe dict."""
    if not doc:
        return {}
    money = lambda k: str(to_money(doc.get(k, 0)))
    return {
        "id": serialize_id(doc.get("_id")),
        "invoice_number": doc.get("invoice_number"),
        "booking_id": serialize_id(doc.get("booking_id")),
        "booking_number": doc.get("booking_number"),
        "customer_id": serialize_id(doc.get("customer_id")),
        "customer_name": doc.get("customer_name"),
        "customer_email": doc.get("customer_email"),
        "issue_date": doc.get("issue_date"),
        "due_date": doc.get("due_date"),
        "line_items": doc.get("line_items", []),
        "subtotal": money("subtotal"),
        "taxable_amount": money("taxable_amount"),
        "total_amount": money("total_amount"),
        "paid_amount": money("paid_amount"),
        "refunded_amount": money("refunded_amount"),
        "remaining_amount": money("remaining_amount"),
        "status": doc.get("status"),
    }


class InvoiceService:
    def __init__(self, repository: InvoiceRepository | None = None):
        self.repository = repository or InvoiceRepository()

    # ---- reads -------------------------------------------------------------
    def list_items(self, **filters) -> list[dict]:
        return [present_invoice(d) for d in self.repository.list_invoices(**filters)]

    def get(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Invoice not found.")
        return present_invoice(doc)

    def _get_raw(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Invoice not found.")
        return doc

    # ---- create from a confirmed booking (the main path) -------------------
    def create_for_booking(self, booking_id: str, *, created_by: str, due_days: int | None = None) -> dict:
        booking = BookingRepository().find_by_id(booking_id)
        if not booking:
            raise NotFoundError("Booking not found.")
        if booking.get("booking_status") not in {BookingStatus.CONFIRMED.value, BookingStatus.COMPLETED.value}:
            raise BusinessRuleViolation("Only a CONFIRMED or COMPLETED booking can be invoiced.")

        existing = self.repository.find_by_booking(booking_id)
        if existing:
            return present_invoice(existing)

        # Denormalize display fields (ERD DN pattern): copy the customer's name and
        # the booking number onto the invoice so list/detail screens never need a join.
        customer = None
        if booking.get("customer_id"):
            customer = get_collection(Collections.CUSTOMERS).find_one(
                {"_id": booking["customer_id"], "is_deleted": {"$ne": True}}
            )
        customer_name = _full_name(customer) if customer else None
        customer_email = (customer or {}).get("email")

        pricing = booking.get("pricing", {})
        subtotal = to_decimal(pricing.get("subtotal", 0))
        discount_amount = to_decimal(pricing.get("discount_amount", 0))
        if discount_amount > subtotal:
            discount_amount = subtotal
        taxable = to_money(subtotal - discount_amount)
        tax_name, tax_rate, tax_amount = _tax_from_settings(pricing, taxable)
        total = to_money(taxable + tax_amount)
        due_days = _invoice_due_days(due_days)

        now = utcnow()
        doc = stamp_new({
            "invoice_number": next_number(Collections.INVOICES),
            "booking_id": booking["_id"],
            "booking_number": booking.get("booking_number"),
            "customer_id": booking.get("customer_id"),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "issue_date": now,
            "due_date": now + timedelta(days=due_days),
            "line_items": [{
                "description": booking.get("notes") or "Tour booking",
                "quantity": int(booking.get("travelers_count", 1)),
                "unit_price": to_decimal128(pricing.get("unit_price", 0)),
                "total": to_decimal128(subtotal),
            }],
            "subtotal": to_decimal128(subtotal),
            "discount": {
                "type": pricing.get("discount_type", "NONE"),
                "value": to_decimal128(pricing.get("discount_value", 0)),
                "amount": to_decimal128(discount_amount),
                "reason": pricing.get("discount_reason"),
                "applied_by": pricing.get("discount_applied_by"),
            },
            "taxable_amount": to_decimal128(taxable),
            "tax": {
                "name": tax_name,
                "rate": to_decimal128(tax_rate),
                "amount": to_decimal128(tax_amount),
                "tax_id": pricing.get("tax_id"),
            },
            "total_amount": to_decimal128(total),
            "paid_amount": to_decimal128(ZERO),
            "refunded_amount": to_decimal128(ZERO),
            "remaining_amount": to_decimal128(total),
            "status": InvoiceStatus.ISSUED.value,
            "live_for_booking": True,
            "currency": booking.get("currency") or DEFAULT_CURRENCY,
            "created_by": parse_object_id(created_by, field="created_by"),
            "created_at": now,
            "updated_at": now,
        })
        try:
            result = self.repository.insert(doc)
        except DuplicateKeyError:
            existing = self.repository.find_by_booking(booking_id)
            if existing:
                return present_invoice(existing)
            raise
        doc["_id"] = result.inserted_id
        presented = present_invoice(doc)
        safe_audit(
            actor_id=created_by,
            action=AuditAction.CREATED.value,
            entity_type="invoices",
            entity_id=doc["_id"],
            description=f"Issued invoice {presented.get('invoice_number')}.",
            after={"invoice_number": presented.get("invoice_number"), "total_amount": presented.get("total_amount")},
        )
        safe_notify_roles(
            FINANCE_NOTIFY_ROLES,
            type=NotificationType.PAYMENT.value,
            title=f"Invoice {presented.get('invoice_number')}",
            message=f"Invoice {presented.get('invoice_number')} was issued for {presented.get('total_amount')}.",
            related_entity_type="invoices",
            related_entity_id=doc["_id"],
            exclude_user_id=created_by,
        )
        return presented

    def cancel(self, doc_id: str, *, actor_id=None) -> dict:
        doc = self._get_raw(doc_id)
        if doc.get("status") == InvoiceStatus.CANCELLED.value:
            return self.get(doc_id)
        paid = to_decimal(doc.get("paid_amount", 0))
        refunded = to_decimal(doc.get("refunded_amount", 0))
        if paid - refunded > ZERO:
            raise BusinessRuleViolation("A paid invoice cannot be cancelled. Record a refund instead.")
        self.repository.update(doc_id, {"status": InvoiceStatus.CANCELLED.value, "live_for_booking": False})
        safe_audit(
            actor_id=actor_id or doc.get("created_by"),
            action=AuditAction.CANCELLED.value,
            entity_type="invoices",
            entity_id=doc["_id"],
            description=f"Cancelled invoice {doc.get('invoice_number')}.",
        )
        return self.get(doc_id)

    def reissue(self, doc_id: str, *, actor_id: str) -> dict:
        """Cancel an unpaid live invoice and issue a fresh one for the same booking."""
        doc = self._get_raw(doc_id)
        booking_id = serialize_id(doc.get("booking_id"))
        if not booking_id:
            raise BusinessRuleViolation("This invoice is not linked to a booking.")
        if doc.get("status") != InvoiceStatus.CANCELLED.value:
            self.cancel(doc_id, actor_id=actor_id)
        return self.create_for_booking(booking_id, created_by=actor_id)

    def money_snapshot(self, invoice_id: str) -> dict:
        return self._money_from(self._get_raw(invoice_id))

    def _money_from(self, inv: dict) -> dict:
        oid = inv["_id"]
        total = to_decimal(inv.get("total_amount", 0))
        payments = get_collection(Collections.PAYMENTS).aggregate([
            {"$match": {"invoice_id": oid, "status": "COMPLETED", "is_deleted": {"$ne": True}}},
            {"$group": {"_id": None, "sum": {"$sum": "$amount"}}},
        ])
        paid = to_decimal(next(iter(payments), {}).get("sum", 0))
        refunds = get_collection(Collections.REFUNDS).aggregate([
            {"$match": {"invoice_id": oid, "status": "COMPLETED", "is_deleted": {"$ne": True}}},
            {"$group": {"_id": None, "sum": {"$sum": "$amount"}}},
        ])
        refunded = to_decimal(next(iter(refunds), {}).get("sum", 0))
        remaining = remaining_due(total, paid)
        if inv.get("status") == InvoiceStatus.CANCELLED.value:
            status = InvoiceStatus.CANCELLED.value
        else:
            status = compute_status(total, paid, refunded)
        return {
            "total": total,
            "paid": paid,
            "refunded": refunded,
            "remaining": remaining,
            "net": to_money(paid - refunded),
            "status": status,
        }

    # ---- rollup recompute, called by PaymentService/RefundService ----------
    def recompute_rollups(self, invoice_id: str) -> dict:
        """Recalculate paid/refunded/remaining/status from payment + refund docs."""
        inv = self._get_raw(invoice_id)
        snap = self._money_from(inv)
        self.repository.set_rollups(
            invoice_id,
            paid=to_decimal128(snap["paid"]),
            refunded=to_decimal128(snap["refunded"]),
            remaining=to_decimal128(snap["remaining"]),
            status=snap["status"],
        )
        return {
            "invoice_id": serialize_id(inv["_id"]),
            "total": str(to_money(snap["total"])),
            "paid": str(to_money(snap["paid"])),
            "refunded": str(to_money(snap["refunded"])),
            "remaining": str(snap["remaining"]),
            "status": snap["status"],
        }
