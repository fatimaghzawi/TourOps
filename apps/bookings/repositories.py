from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class BookingRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        tours: Collection | None = None,
        customers: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.BOOKINGS)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)
        self.customers = customers if customers is not None else get_collection(Collections.CUSTOMERS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="booking_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def list_bookings(self, extra: dict | None = None) -> list[dict]:
        return list(self.collection.find(live_query(extra)).sort("created_at", -1))

    def list_for_tour(self, tour_id: str | ObjectId) -> list[dict]:
        return self.list_bookings({"tour_id": parse_object_id(tour_id, field="tour_id")})

    def find_tour(self, tour_id: str | ObjectId) -> dict | None:
        return self.tours.find_one(live_query({"_id": parse_object_id(tour_id, field="tour_id")}))

    def find_customer(self, customer_id: str | ObjectId) -> dict | None:
        return self.customers.find_one(live_query({"_id": parse_object_id(customer_id, field="customer_id")}))

    def update_if(self, doc_id: str | ObjectId, *, expected: dict, updates: dict):
        query = live_query({"_id": parse_object_id(doc_id, field="booking_id"), **(expected or {})})
        return self.collection.update_one(query, {"$set": updates})
