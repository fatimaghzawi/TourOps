"""Receipt reads.  OWNER: Dev 3 — Customer Finance

There is NO create method here on purpose. Receipts are issued automatically
inside PaymentService when a payment reaches COMPLETED.
"""
from __future__ import annotations

from apps.receipts.repositories import ReceiptRepository
from core.exceptions import NotFoundError
from core.money import to_money
from core.utils import serialize_id


def present_receipt(doc: dict) -> dict:
    if not doc:
        return {}
    return {
        "id": serialize_id(doc.get("_id")),
        "receipt_number": doc.get("receipt_number"),
        "payment_id": serialize_id(doc.get("payment_id")),
        "invoice_id": serialize_id(doc.get("invoice_id")),
        "customer_id": serialize_id(doc.get("customer_id")),
        "amount": str(to_money(doc.get("amount", 0))),
        "payment_method": doc.get("payment_method"),
        "issued_at": doc.get("issued_at"),
    }


class ReceiptService:
    def __init__(self, repository: ReceiptRepository | None = None):
        self.repository = repository or ReceiptRepository()

    def get(self, doc_id: str) -> dict:
        doc = self.repository.find_by_id(doc_id)
        if not doc:
            raise NotFoundError("Receipt not found.")
        return present_receipt(doc)

    def list_items(self, **filters) -> list[dict]:
        return [present_receipt(doc) for doc in self.repository.list_receipts(**filters)]

    def for_payment(self, payment_id: str) -> dict:
        doc = self.repository.find_by_payment(payment_id)
        if not doc:
            raise NotFoundError("No receipt for this payment yet.")
        return present_receipt(doc)
