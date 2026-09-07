from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.money import ZERO, money_dict, to_money
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class SupplierPaymentRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        expenses: Collection | None = None,
        suppliers: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.SUPPLIER_PAYMENTS)
        self.expenses = expenses if expenses is not None else get_collection(Collections.EXPENSES)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)

    def _hydrate(self, document: dict | None) -> dict | None:
        if not document:
            return None
        return money_dict(document, "amount")

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="payment_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self._hydrate(self.collection.find_one(query))

    def list_payments(self, extra: dict | None = None) -> list[dict]:
        return [self._hydrate(doc) for doc in self.collection.find(live_query(extra)).sort("payment_date", -1)]

    def list_by_expense(self, expense_id: str | ObjectId) -> list[dict]:
        return self.list_payments({"expense_id": parse_object_id(expense_id, field="expense_id")})

    def list_by_supplier(self, supplier_id: str | ObjectId) -> list[dict]:
        return self.list_payments({"supplier_id": parse_object_id(supplier_id, field="supplier_id")})

    def sum_for_expense(self, expense_id: str | ObjectId):
        total = ZERO
        for document in self.list_by_expense(expense_id):
            total += to_money(document.get("amount"))
        return total

    def find_expense(self, expense_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(expense_id, field="expense_id")})
        document = self.expenses.find_one(query)
        if not document:
            return None
        return money_dict(document, "amount", "paid_amount", "remaining_amount")

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(supplier_id, field="supplier_id")})
        return self.suppliers.find_one(query)
