from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id, utcnow


class NotificationRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.NOTIFICATIONS)

    def list_for_user(
        self,
        user_id,
        *,
        unread_only: bool = False,
        notification_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query: dict = {"user_id": parse_object_id(user_id, field="user_id")}
        if unread_only:
            query["is_read"] = False
        if notification_type:
            query["type"] = notification_type
        return list(self.collection.find(live_query(query)).sort("created_at", -1).limit(limit))

    def count_unread(self, user_id) -> int:
        return self.collection.count_documents(
            live_query({"user_id": parse_object_id(user_id, field="user_id"), "is_read": False})
        )

    def mark_read(self, doc_id, user_id) -> int:
        result = self.collection.update_one(
            live_query(
                {
                    "_id": parse_object_id(doc_id),
                    "user_id": parse_object_id(user_id, field="user_id"),
                }
            ),
            {"$set": {"is_read": True, "read_at": utcnow()}},
        )
        return result.matched_count

    def mark_all_read(self, user_id) -> int:
        result = self.collection.update_many(
            live_query({"user_id": parse_object_id(user_id, field="user_id"), "is_read": False}),
            {"$set": {"is_read": True, "read_at": utcnow()}},
        )
        return result.modified_count
