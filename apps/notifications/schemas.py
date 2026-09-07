from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.schemas import RelatedEntity


@dataclass
class NotificationDocument:
    user_id: ObjectId
    type: str
    title: str
    message: str
    created_at: datetime
    related_entity: Optional[RelatedEntity] = None
    is_read: bool = False
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
