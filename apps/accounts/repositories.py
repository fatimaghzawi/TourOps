from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections, UserRole, UserStatus
from core.database import get_collection
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query, stamp_new
from core.utils import parse_object_id


class UserRepository(SoftDeleteRepositoryMixin):
    def __init__(self, collection: Collection | None = None):
        self.collection = collection or get_collection(Collections.USERS)

    def find_by_email(self, email: str, *, include_deleted: bool = False) -> dict | None:
        query = {"email": email.strip().lower()}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def find_by_id(self, user_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(user_id, field="user_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def insert(self, document: dict):
        return self.collection.insert_one(stamp_new(document))

    def update_last_login(self, user_id, when) -> None:
        self.collection.update_one(live_query({"_id": user_id}), {"$set": {"last_login_at": when}})

    def list_users(self, *, include_deleted: bool = False) -> list[dict]:
        query = {} if include_deleted else live_query()
        return list(self.collection.find(query).sort("created_at", -1))

    def list_active(self) -> list[dict]:
        return list(self.collection.find(live_query({"status": UserStatus.ACTIVE.value})))

    def count_live(self, extra: dict | None = None) -> int:
        return self.collection.count_documents(live_query(extra))

    def count_active_owners(self, exclude_id: str | ObjectId | None = None) -> int:
        query = live_query({"role": UserRole.OWNER_ADMIN.value, "status": UserStatus.ACTIVE.value})
        if exclude_id is not None:
            query["_id"] = {"$ne": parse_object_id(exclude_id, field="user_id")}
        return self.collection.count_documents(query)
