from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from apps.expenses.constants import MONEY_FIELDS
from core.constants import Collections
from core.database import get_collection
from core.money import ZERO, money_dict, to_money
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class SupplierRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        expenses: Collection | None = None,
        tours: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.SUPPLIERS)
        self.expenses = expenses if expenses is not None else get_collection(Collections.EXPENSES)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="supplier_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def list_suppliers(self, extra: dict | None = None) -> list[dict]:
        return list(self.collection.find(live_query(extra)).sort("name", 1))

    def remaining_by_supplier(self) -> dict[str, object]:
        totals: dict[str, object] = {}
        for document in self.expenses.find(live_query()):
            hydrated = money_dict(document, *MONEY_FIELDS)
            supplier_id = hydrated.get("supplier_id")
            if not supplier_id:
                continue
            key = str(supplier_id)
            totals[key] = to_money(totals.get(key, ZERO)) + to_money(hydrated.get("remaining_amount"))
        return totals

    def list_expenses_for(self, supplier_id: str | ObjectId) -> list[dict]:
        query = live_query({"supplier_id": parse_object_id(supplier_id, field="supplier_id")})
        return [
            money_dict(document, *MONEY_FIELDS)
            for document in self.expenses.find(query).sort("expense_date", -1)
        ]

    def list_tours_for(self, supplier_id: str | ObjectId) -> list[dict]:
        oid = parse_object_id(supplier_id, field="supplier_id")
        found: dict[str, dict] = {}
        for expense in self.list_expenses_for(oid):
            tour_id = expense.get("tour_id")
            if not tour_id:
                continue
            tour = self.tours.find_one(live_query({"_id": tour_id}))
            if tour:
                found[str(tour["_id"])] = tour
        for tour in self.tours.find(live_query()):
            for line in tour.get("services") or []:
                if not isinstance(line, dict):
                    continue
                if str(line.get("supplier_id") or "") == str(oid):
                    found[str(tour["_id"])] = tour
        return list(found.values())
