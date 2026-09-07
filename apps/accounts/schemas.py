from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.constants import UserRole, UserStatus


@dataclass
class UserDocument:
    first_name: str
    last_name: str
    email: str
    password_hash: str
    role: str
    created_at: datetime
    updated_at: datetime
    phone: Optional[str] = None
    status: str = UserStatus.ACTIVE.value
    last_login_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None

    ALLOWED_ROLES = {item.value for item in UserRole}
    ALLOWED_STATUSES = {item.value for item in UserStatus}


USER_DOCUMENT_EXAMPLE = {
    "_id": "ObjectId",
    "first_name": "Amina",
    "last_name": "Hassan",
    "email": "owner@tourops.local",
    "password_hash": "django-pbkdf2-sha256$...",
    "role": "OWNER_ADMIN",
    "phone": None,
    "status": "ACTIVE",
    "last_login_at": None,
    "is_deleted": False,
    "deleted_at": None,
    "deleted_by": None,
    "created_at": "datetime",
    "updated_at": "datetime",
}
