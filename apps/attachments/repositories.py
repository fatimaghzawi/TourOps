from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class AttachmentRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.ATTACHMENTS)

    def list_for_entity(self, entity_type: str, entity_id, *, limit: int = 100) -> list[dict]:
        return list(
            self.collection.find(
                live_query(
                    {
                        "entity_type": entity_type,
                        "entity_id": parse_object_id(entity_id, field="entity_id"),
                    }
                )
            )
            .sort("created_at", -1)
            .limit(limit)
        )

    def list_items(
        self,
        *,
        entity_type: str | None = None,
        entity_types=None,
        entity_id=None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query: dict = {}
        if entity_type:
            query["entity_type"] = entity_type
        elif entity_types:
            query["entity_type"] = {"$in": list(entity_types)}
        if entity_id:
            query["entity_id"] = parse_object_id(entity_id, field="entity_id")
        if category:
            query["category"] = category
        return list(self.collection.find(live_query(query)).sort("created_at", -1).limit(limit))
