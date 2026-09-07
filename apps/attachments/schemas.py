from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bson import ObjectId


@dataclass
class AttachmentDocument:
    entity_type: str
    entity_id: ObjectId
    category: str
    file_name: str
    content_type: str
    storage_key: str
    uploaded_by: ObjectId
    created_at: datetime
    notes: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
