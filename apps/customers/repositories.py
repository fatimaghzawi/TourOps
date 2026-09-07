from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class CustomerRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.CUSTOMERS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="customer_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def find_by_email(self, email: str) -> dict | None:
        return self.collection.find_one(live_query({"email": email}))

    def find_all(
        self,
        limit: int = 50,
        *,
        query: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> list[dict]:
        filters: dict = {}
        if query:
            filters["$or"] = [
                {"first_name": {"$regex": query, "$options": "i"}},
                {"last_name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
                {"phone": {"$regex": query, "$options": "i"}},
                {"customer_number": {"$regex": query, "$options": "i"}},
            ]
        if status:
            filters["status"] = status
        query_filter = filters if include_deleted else live_query(filters)
        return list(self.collection.find(query_filter).sort("last_name", 1).limit(limit))

    def list_customers(self, extra: dict | None = None) -> list[dict]:
        return list(self.collection.find(live_query(extra)).sort("last_name", 1))
