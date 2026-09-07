"""MongoDB access for receipts.  OWNER: Dev 3 — Customer Finance

Receipts are auto-created by PaymentService when a payment completes.
This repository is read-only in practice — no public create path.
"""
from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class ReceiptRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.RECEIPTS)

    def find_by_payment(self, payment_id) -> dict | None:
        return self.collection.find_one(live_query({
            "payment_id": parse_object_id(payment_id, field="payment_id"),
        }))

    def list_receipts(self, *, customer_id=None, payment_id=None, invoice_id=None, limit: int = 100) -> list[dict]:
        query: dict = {}
        if customer_id:
            query["customer_id"] = parse_object_id(customer_id, field="customer_id")
        if payment_id:
            query["payment_id"] = parse_object_id(payment_id, field="payment_id")
        if invoice_id:
            query["invoice_id"] = parse_object_id(invoice_id, field="invoice_id")
        return list(self.collection.find(live_query(query)).sort("issued_at", -1).limit(limit))
