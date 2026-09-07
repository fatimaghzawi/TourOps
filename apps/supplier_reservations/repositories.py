from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class SupplierReservationRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        tours: Collection | None = None,
        suppliers: Collection | None = None,
        bookings: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.SUPPLIER_RESERVATIONS)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)
        self.bookings = bookings if bookings is not None else get_collection(Collections.BOOKINGS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="reservation_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def list_reservations(self, extra: dict | None = None) -> list[dict]:
        return list(self.collection.find(live_query(extra)).sort("start_date", 1))

    def list_for_tour(self, tour_id: str | ObjectId) -> list[dict]:
        return self.list_reservations({"tour_id": parse_object_id(tour_id, field="tour_id")})

    def find_tour(self, tour_id: str | ObjectId) -> dict | None:
        return self.tours.find_one(live_query({"_id": parse_object_id(tour_id, field="tour_id")}))

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        return self.suppliers.find_one(live_query({"_id": parse_object_id(supplier_id, field="supplier_id")}))

    def list_suppliers(self) -> list[dict]:
        return list(self.suppliers.find(live_query()).sort("name", 1))
