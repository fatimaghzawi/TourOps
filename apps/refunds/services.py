"""
Refund business rules.  OWNER: Dev 3 — Customer Finance

- A refund is a NEW document. The original payment is never edited or deleted.
- Amount = amount_paid * tier% , but NEVER more than the amount actually paid.
- Lifecycle: PENDING -> APPROVED -> COMPLETED  (or -> REJECTED).
- Only a COMPLETED refund counts as cash-out and moves invoice/booking status.
- Tier %s are config-driven (REFUND_TIERS) so a policy change lives in one place.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.invoices.services import InvoiceService
from apps.notifications.constants import NotificationType
from apps.notifications.services import notify_for_type
from apps.payments.repositories import PaymentRepository
from apps.payments.services import _sync_booking_payment_status
from apps.refunds.repositories import RefundRepository
from core.constants import (
    Collections,
    PaymentRecordStatus,
    RefundPolicyTier,
    RefundStatus,
)
from core.database import get_collection
from core.exceptions import BusinessRuleViolation, NotFoundError, ValidationError
from core.money import ZERO, to_decimal, to_decimal128, to_money
from core.numbering import next_number
from core.soft_delete import stamp_new
from core.utils import parse_object_id, serialize_id, utcnow

POLICY_VERSION = "2026-01"

OPEN_REFUND_STATUSES = {
    RefundStatus.PENDING.value,
    RefundStatus.APPROVED.value,
    RefundStatus.COMPLETED.value,
}

# Refund % of amount paid, by tier. Matches the Dev 3 spec / BRD.
REFUND_TIERS = {
    RefundPolicyTier.DAYS_30_PLUS.value: Decimal("0.90"),
    RefundPolicyTier.DAYS_15_TO_29.value: Decimal("0.70"),
    RefundPolicyTier.DAYS_7_TO_14.value: Decimal("0.50"),
    RefundPolicyTier.UNDER_7.value: Decimal("0.00"),
    RefundPolicyTier.AGENCY_CANCEL.value: Decimal("1.00"),
}


def tier_for_days(days_before: int) -> str:
    if days_before >= 30:
        return RefundPolicyTier.DAYS_30_PLUS.value
    if days_before >= 15:
        return RefundPolicyTier.DAYS_15_TO_29.value
    if days_before >= 7:
        return RefundPolicyTier.DAYS_7_TO_14.value
    return RefundPolicyTier.UNDER_7.value


def present_refund(doc: dict) -> dict:
    if not doc:
        return {}
    return {
        "id": serialize_id(doc.get("_id")),
        "refund_number": doc.get("refund_number"),
        "payment_id": serialize_id(doc.get("payment_id")),
        "invoice_id": serialize_id(doc.get("invoice_id")),
        "booking_id": serialize_id(doc.get("booking_id")),
        "customer_id": serialize_id(doc.get("customer_id")),
        "amount": str(to_money(doc.get("amount", 0))),
        "reason": doc.get("reason"),
        "refund_method": doc.get("refund_method"),
        "status": doc.get("status"),
        "policy_tier": doc.get("policy_tier"),
        "policy_version": doc.get("policy_version"),
        "refund_percent": str(to_decimal(doc.get("refund_percent", 0))) if doc.get("refund_percent") is not None else None,
        "retained_fee_amount": str(to_money(doc.get("retained_fee_amount", 0))),
    }


class RefundService:
    def __init__(self, repository: RefundRepository | None = None):
        self.repository = repository or RefundRepository()
        self.invoices = InvoiceService()
        self.payments = PaymentRepository()

    def list_items(self, **filters) -> list[dict]:
        return [present_refund(d) for d in self.repository.list_refunds(**filters)]

    def get(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Refund not found.")
        return present_refund(doc)

    def _get_raw(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Refund not found.")
        return doc

    # ---- create a refund request from a payment (the main path) ------------
    def create_from_payment(self, payment_id: str, *, reason: str, refund_method: str,
                            requested_by: str, tier: str | None = None,
                            days_before: int | None = None, amount=None,
                            direct: bool = False) -> dict:
        payment = get_collection(Collections.PAYMENTS).find_one({
            "_id": parse_object_id(payment_id, field="payment_id"),
            "is_deleted": {"$ne": True},
        })
        if not payment:
            raise NotFoundError("Payment not found.")
        if payment.get("status") != PaymentRecordStatus.COMPLETED.value:
            raise BusinessRuleViolation("Only a COMPLETED payment can be refunded.")

        paid = to_decimal(payment.get("amount", 0))
        self._ensure_refundable_remaining(payment)
        eligible = self.remaining_refundable(payment)

        # Resolve tier: explicit tier wins, else derive from days_before.
        if tier is None and days_before is not None:
            tier = tier_for_days(days_before)
        if tier is None:
            raise ValidationError("Provide a policy tier or days_before.")

        if tier == RefundPolicyTier.OTHER.value:
            if amount is None:
                raise ValidationError("OTHER refunds require an explicit amount.")
            refund_amount = to_money(amount)
            percent = to_money(refund_amount / paid) if paid > ZERO else ZERO
        else:
            if tier not in REFUND_TIERS:
                raise ValidationError(f"Unknown policy tier {tier!r}.")
            percent = REFUND_TIERS[tier]
            computed = to_money(paid * percent)
            if amount is not None:
                refund_amount = to_money(amount)
                if refund_amount > computed:
                    raise BusinessRuleViolation(
                        f"Refund {refund_amount} exceeds the policy cap of {computed} for this cancellation window."
                    )
            else:
                refund_amount = computed

        if refund_amount <= ZERO:
            if amount is not None:
                raise ValidationError("Refund amount must be greater than zero.")
            raise ValidationError("This cancellation window does not allow a refund.")

        if refund_amount > eligible:
            raise BusinessRuleViolation(
                f"Refund {refund_amount} exceeds remaining refundable amount {eligible}."
            )

        retained = to_money(paid - refund_amount)
        reserved = self.payments.try_consume_refundable(payment["_id"], refund_amount)
        if not reserved:
            raise BusinessRuleViolation(
                f"Refund {refund_amount} exceeds remaining refundable amount {eligible}."
            )
        now = utcnow()
        actor = parse_object_id(requested_by, field="requested_by")
        doc = stamp_new({
            "refund_number": next_number(Collections.REFUNDS),
            "payment_id": payment["_id"],
            "invoice_id": payment.get("invoice_id"),
            "booking_id": payment.get("booking_id"),
            "customer_id": payment.get("customer_id"),
            "amount": to_decimal128(refund_amount),
            "reason": reason,
            "refund_method": refund_method,
            "status": RefundStatus.COMPLETED.value if direct else RefundStatus.PENDING.value,
            "policy_tier": tier,
            "policy_version": POLICY_VERSION,
            "refund_percent": to_decimal128(percent),
            "deposit_excluded_amount": to_decimal128(ZERO),
            "retained_fee_amount": to_decimal128(retained),
            "approved_at": now if direct else None,
            "approved_by": actor if direct else None,
            "processed_at": now if direct else None,
            "processed_by": actor if direct else None,
            "created_by": actor,
            "created_at": now,
        })
        try:
            result = self.repository.insert(doc)
        except Exception:
            self.payments.release_refundable(payment["_id"], refund_amount)
            raise
        doc["_id"] = result.inserted_id
        presented = present_refund(doc)
        if direct:
            self._apply_payout(doc, actor_id=requested_by)
            presented = self.get(serialize_id(doc["_id"]))
            safe_audit(
                actor_id=requested_by,
                action=AuditAction.COMPLETED.value,
                entity_type="refunds",
                entity_id=doc["_id"],
                description=f"Issued refund {presented.get('refund_number')}.",
                after={"refund_number": presented.get("refund_number"), "amount": presented.get("amount")},
            )
            self._notify_paid(presented, actor_id=requested_by)
            return presented
        safe_audit(
            actor_id=requested_by,
            action=AuditAction.CREATED.value,
            entity_type="refunds",
            entity_id=doc["_id"],
            description=f"Requested refund {presented.get('refund_number')}.",
            after={"refund_number": presented.get("refund_number"), "amount": presented.get("amount")},
        )
        notify_for_type(
            NotificationType.REFUND.value,
            title=f"Refund {presented.get('refund_number')}",
            message=f"A refund of {presented.get('amount')} is waiting for approval.",
            related_entity_type="refunds",
            related_entity_id=doc["_id"],
            exclude_user_id=requested_by,
        )
        return presented

    def remaining_refundable(self, payment: dict):
        if payment.get("refundable_remaining") is not None:
            leftover = to_money(payment.get("refundable_remaining"))
            return leftover if leftover > ZERO else ZERO
        paid = to_decimal(payment.get("amount", 0))
        reserved = ZERO
        for existing in self.repository.list_refunds(payment_id=payment["_id"]):
            if existing.get("status") in OPEN_REFUND_STATUSES:
                reserved += to_decimal(existing.get("amount", 0))
        leftover = to_money(paid - reserved)
        return leftover if leftover > ZERO else ZERO

    def _ensure_refundable_remaining(self, payment: dict) -> None:
        if payment.get("refundable_remaining") is not None:
            return
        leftover = self.remaining_refundable(payment)
        from pymongo.errors import PyMongoError

        try:
            self.payments.collection.update_one(
                {
                    "_id": payment["_id"],
                    "refundable_remaining": {"$exists": False},
                    "is_deleted": {"$ne": True},
                },
                {"$set": {"refundable_remaining": to_decimal128(leftover)}},
            )
        except PyMongoError:
            pass
        payment["refundable_remaining"] = leftover

    # ---- lifecycle actions -------------------------------------------------
    def approve(self, refund_id: str, *, actor_id: str) -> dict:
        doc = self._get_raw(refund_id)
        if doc.get("status") != RefundStatus.PENDING.value:
            raise BusinessRuleViolation("Only a PENDING refund can be approved.")
        self.repository.set_status(
            refund_id, RefundStatus.APPROVED.value,
            actor_id=parse_object_id(actor_id, field="approved_by"), stamp_field="approved_by",
        )
        presented = self.get(refund_id)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.APPROVED.value,
            entity_type="refunds",
            entity_id=doc["_id"],
            description=f"Approved refund {presented.get('refund_number')}.",
        )
        return presented

    def reject(self, refund_id: str, *, actor_id: str) -> dict:
        doc = self._get_raw(refund_id)
        if doc.get("status") not in {RefundStatus.PENDING.value, RefundStatus.APPROVED.value}:
            raise BusinessRuleViolation("Only a PENDING or APPROVED refund can be rejected.")
        self.repository.set_status(
            refund_id, RefundStatus.REJECTED.value,
            actor_id=parse_object_id(actor_id, field="processed_by"), stamp_field="processed_by",
        )
        self.payments.release_refundable(doc["payment_id"], to_money(doc.get("amount")))
        presented = self.get(refund_id)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.REJECTED.value,
            entity_type="refunds",
            entity_id=doc["_id"],
            description=f"Rejected refund {presented.get('refund_number')}.",
        )
        return presented

    def complete(self, refund_id: str, *, actor_id: str) -> dict:
        doc = self._get_raw(refund_id)
        if doc.get("status") != RefundStatus.APPROVED.value:
            raise BusinessRuleViolation("Only an APPROVED refund can be completed.")
        self.repository.set_status(
            refund_id, RefundStatus.COMPLETED.value,
            actor_id=parse_object_id(actor_id, field="processed_by"), stamp_field="processed_by",
        )
        doc = self._get_raw(refund_id)
        self._apply_payout(doc, actor_id=actor_id)
        presented = self.get(refund_id)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.COMPLETED.value,
            entity_type="refunds",
            entity_id=doc["_id"],
            description=f"Completed refund {presented.get('refund_number')}.",
        )
        self._notify_paid(presented, actor_id=actor_id)
        return presented

    def _apply_payout(self, doc: dict, *, actor_id: str) -> None:
        self.invoices.recompute_rollups(serialize_id(doc["invoice_id"]))
        _sync_booking_payment_status(doc.get("booking_id"))

    def _notify_paid(self, presented: dict, *, actor_id: str) -> None:
        notify_for_type(
            NotificationType.REFUND.value,
            title=f"Refund {presented.get('refund_number')} paid",
            message=f"Refund {presented.get('refund_number')} of {presented.get('amount')} was completed.",
            related_entity_type="refunds",
            related_entity_id=presented.get("id"),
            exclude_user_id=actor_id,
        )
