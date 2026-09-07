from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.utils import parse_object_id


class AuditLogRepository:
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.AUDIT_LOGS)

    def find_all(
        self,
        *,
        user_id=None,
        action: str | None = None,
        entity_type: str | None = None,
        date_from=None,
        date_to=None,
        limit: int = 100,
    ) -> list[dict]:
        query: dict = {}
        if user_id:
            query["user_id"] = parse_object_id(user_id, field="user_id")
        if action:
            query["action"] = action
        if entity_type:
            query["entity_type"] = entity_type
        when: dict = {}
        if date_from is not None:
            when["$gte"] = date_from
        if date_to is not None:
            when["$lte"] = date_to
        if when:
            query["created_at"] = when
        return list(self.collection.find(query).sort("created_at", -1).limit(limit))

    def find_by_id(self, doc_id: str) -> dict | None:
        return self.collection.find_one({"_id": parse_object_id(doc_id)})

    def find_for_entity(self, entity_type: str, entity_id, *, limit: int = 50) -> list[dict]:
        return list(
            self.collection.find(
                {
                    "entity_type": entity_type,
                    "entity_id": parse_object_id(entity_id, field="entity_id"),
                }
            )
            .sort("created_at", -1)
            .limit(limit)
        )

    def insert(self, document: dict):
        return self.collection.insert_one(document)
