from __future__ import annotations

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from apps.expenses.constants import MONEY_FIELDS
from core.constants import Collections
from core.database import get_collection
from core.money import money_dict, to_decimal128, to_money
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class ExpenseRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        suppliers: Collection | None = None,
        tours: Collection | None = None,
        supplier_payments: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.EXPENSES)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)
        self.supplier_payments = (
            supplier_payments if supplier_payments is not None else get_collection(Collections.SUPPLIER_PAYMENTS)
        )

    def _hydrate(self, document: dict | None) -> dict | None:
        if not document:
            return None
        return money_dict(document, *MONEY_FIELDS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="expense_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self._hydrate(self.collection.find_one(query))

    def list_expenses(self, extra: dict | None = None) -> list[dict]:
        return [self._hydrate(doc) for doc in self.collection.find(live_query(extra)).sort("expense_date", -1)]

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(supplier_id, field="supplier_id")})
        return self.suppliers.find_one(query)

    def find_tour(self, tour_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(tour_id, field="tour_id")})
        return self.tours.find_one(query)

    def list_suppliers(self) -> list[dict]:
        return list(self.suppliers.find(live_query()).sort("name", 1))

    def list_tours(self) -> list[dict]:
        return list(self.tours.find(live_query()).sort("name", 1))

    def list_payments_for_expense(self, expense_id: str | ObjectId) -> list[dict]:
        query = live_query({"expense_id": parse_object_id(expense_id, field="expense_id")})
        docs = list(self.supplier_payments.find(query).sort("payment_date", -1))
        return [money_dict(doc, "amount") for doc in docs]

    def try_consume_remaining(self, expense_id, amount) -> dict | None:
        money = to_money(amount)
        if money <= 0:
            return None
        encoded = to_decimal128(money)
        return self.collection.find_one_and_update(
            live_query(
                {
                    "_id": parse_object_id(expense_id, field="expense_id"),
                    "remaining_amount": {"$gte": encoded},
                }
            ),
            {"$inc": {"remaining_amount": to_decimal128(-money), "paid_amount": encoded}},
            return_document=ReturnDocument.AFTER,
        )
