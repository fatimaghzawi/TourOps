from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from core.exceptions import ValidationError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_object_id(value: str | ObjectId, *, field: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError) as exc:
        raise ValidationError(f"Invalid {field}.") from exc


def serialize_id(value: ObjectId | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def full_name(first: str | None, last: str | None) -> str:
    return " ".join(part for part in (first or "", last or "") if part).strip()
