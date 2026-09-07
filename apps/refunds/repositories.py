"""MongoDB access for refunds.  OWNER: Dev 3 — Customer Finance"""
from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections, RefundStatus
from core.database import get_collection
from core.soft_delete import SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id, utcnow


class RefundRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.REFUNDS)

    def list_refunds(self, *, customer_id=None, status=None, payment_id=None, limit: int = 100) -> list[dict]:
        query: dict = {}
        if customer_id:
            query["customer_id"] = parse_object_id(customer_id, field="customer_id")
        if payment_id:
            query["payment_id"] = parse_object_id(payment_id, field="payment_id")
        if status:
            query["status"] = status
        return list(self.collection.find(live_query(query)).sort("created_at", -1).limit(limit))

    def completed_total_for_payment(self, payment_id) -> dict | None:
        cursor = self.collection.aggregate([
            {"$match": {
                "payment_id": parse_object_id(payment_id, field="payment_id"),
                "status": RefundStatus.COMPLETED.value,
                "is_deleted": {"$ne": True},
            }},
            {"$group": {"_id": None, "sum": {"$sum": "$amount"}}},
        ])
        return next(iter(cursor), None)

    def set_status(self, refund_id, status: str, *, actor_id=None, stamp_field: str | None = None) -> None:
        updates = {"status": status, "updated_at": utcnow()}
        if stamp_field and actor_id is not None:
            updates[stamp_field] = actor_id
            updates[stamp_field.replace("_by", "_at")] = utcnow()
        self.collection.update_one(
            live_query({"_id": parse_object_id(refund_id, field="refund_id")}),
            {"$set": updates},
        )
