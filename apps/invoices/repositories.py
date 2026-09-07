"""
MongoDB access for invoices.  OWNER: Dev 3 — Customer Finance
Queries exclude soft-deleted rows by default. Never call delete_one().
"""
from __future__ import annotations

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from core.constants import Collections, InvoiceStatus
from core.database import get_collection
from core.money import to_decimal128, to_money
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class InvoiceRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.INVOICES)

    def list_invoices(self, *, customer_id=None, status=None, booking_id=None, limit: int = 100) -> list[dict]:
        query: dict = {}
        if customer_id:
            query["customer_id"] = parse_object_id(customer_id, field="customer_id")
        if booking_id:
            query["booking_id"] = parse_object_id(booking_id, field="booking_id")
        if status:
            query["status"] = status
        return list(self.collection.find(live_query(query)).sort("created_at", -1).limit(limit))

    def find_by_booking(self, booking_id, *, include_cancelled: bool = False) -> dict | None:
        """Return the live invoice for a booking. Used to enforce 1 live invoice per booking."""
        query = live_query({"booking_id": parse_object_id(booking_id, field="booking_id")})
        if not include_cancelled:
            query["status"] = {"$ne": InvoiceStatus.CANCELLED.value}
        return self.collection.find_one(query)

    def try_consume_remaining(self, invoice_id, amount) -> dict | None:
        money = to_money(amount)
        if money <= 0:
            return None
        encoded = to_decimal128(money)
        return self.collection.find_one_and_update(
            live_query(
                {
                    "_id": parse_object_id(invoice_id, field="invoice_id"),
                    "status": {"$nin": [InvoiceStatus.CANCELLED.value, InvoiceStatus.REFUNDED.value]},
                    "remaining_amount": {"$gte": encoded},
                }
            ),
            {"$inc": {"remaining_amount": to_decimal128(-money), "paid_amount": encoded}},
            return_document=ReturnDocument.AFTER,
        )

    def set_rollups(self, invoice_id, *, paid, refunded, remaining, status) -> None:
        """Overwrite the stored payment rollups + status after a payment/refund posts."""
        from core.utils import utcnow
        self.collection.update_one(
            live_query({"_id": parse_object_id(invoice_id, field="invoice_id")}),
            {"$set": {
                "paid_amount": paid,
                "refunded_amount": refunded,
                "remaining_amount": remaining,
                "status": status,
                "updated_at": utcnow(),
            }},
        )
