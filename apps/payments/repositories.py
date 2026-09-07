"""MongoDB access for payments.  OWNER: Dev 3 — Customer Finance"""
from __future__ import annotations

from pymongo import ReturnDocument
from pymongo.collection import Collection

from core.constants import Collections, PaymentRecordStatus
from core.database import get_collection
from core.money import to_decimal128, to_money
from core.soft_delete import SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class PaymentRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.PAYMENTS)

    def list_payments(self, *, invoice_id=None, customer_id=None, limit: int = 100) -> list[dict]:
        query: dict = {}

        if invoice_id:
            query["invoice_id"] = parse_object_id(
                invoice_id,
                field="invoice_id"
            )

        if customer_id:
            query["customer_id"] = parse_object_id(
                customer_id,
                field="customer_id"
            )

        return list(
            self.collection.find(
                live_query(query)
            ).sort("created_at", -1).limit(limit)
        )

    def find_for_invoice(self, invoice_id) -> list[dict]:
        return list(
            self.collection.find(
                live_query({
                    "invoice_id": parse_object_id(
                        invoice_id,
                        field="invoice_id"
                    ),
                })
            ).sort("created_at", 1)
        )

    def find_for_booking(self, booking_id) -> list[dict]:
        return list(
            self.collection.find(
                live_query({
                    "booking_id": parse_object_id(
                        booking_id,
                        field="booking_id",
                    ),
                    "status": PaymentRecordStatus.COMPLETED.value,
                })
            ).sort("created_at", 1)
        )

    def find_completed_by_reference(self, invoice_id, reference_number: str) -> dict | None:
        return self.collection.find_one(live_query({
            "invoice_id": parse_object_id(invoice_id, field="invoice_id"),
            "reference_number": reference_number,
            "status": PaymentRecordStatus.COMPLETED.value,
        }))

    def find_recent_duplicate(self, invoice_id, *, amount, method, recorded_by, since) -> dict | None:
        money = to_money(amount)
        latest = self.collection.find(
            live_query(
                {
                    "invoice_id": parse_object_id(invoice_id, field="invoice_id"),
                    "status": PaymentRecordStatus.COMPLETED.value,
                }
            )
        ).sort("created_at", -1).limit(1)
        for doc in latest:
            created = doc.get("created_at")
            if created is None or created < since:
                return None
            if doc.get("reference_number"):
                return None
            if doc.get("payment_method") != method:
                return None
            if str(doc.get("recorded_by")) != str(parse_object_id(recorded_by, field="recorded_by")):
                return None
            if to_money(doc.get("amount")) != money:
                return None
            return doc
        return None

    def try_consume_refundable(self, payment_id, amount) -> dict | None:
        money = to_money(amount)
        if money <= 0:
            return None
        encoded = to_decimal128(money)
        return self.collection.find_one_and_update(
            live_query(
                {
                    "_id": parse_object_id(payment_id, field="payment_id"),
                    "status": PaymentRecordStatus.COMPLETED.value,
                    "refundable_remaining": {"$gte": encoded},
                }
            ),
            {"$inc": {"refundable_remaining": to_decimal128(-money)}},
            return_document=ReturnDocument.AFTER,
        )

    def release_refundable(self, payment_id, amount) -> None:
        money = to_money(amount)
        if money <= 0:
            return
        self.collection.update_one(
            live_query(
                {
                    "_id": parse_object_id(payment_id, field="payment_id"),
                    "status": PaymentRecordStatus.COMPLETED.value,
                }
            ),
            {"$inc": {"refundable_remaining": to_decimal128(money)}},
        )

    def mark_voided(self, payment_id) -> None:
        from core.utils import utcnow

        self.collection.update_one(
            live_query({
                "_id": parse_object_id(
                    payment_id,
                    field="payment_id"
                )
            }),
            {
                "$set": {
                    "status": PaymentRecordStatus.VOIDED.value,
                    "updated_at": utcnow()
                }
            },
        )
