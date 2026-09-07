from __future__ import annotations

from apps.suppliers.constants import INT_INFO_FIELDS, LIST_INFO_FIELDS, PREFERRED_METHODS
from apps.suppliers.schemas import SupplierDocument
from core.constants import RecordStatus
from core.exceptions import ValidationError


def validate_type(value: str) -> str:
    supplier_type = (value or "").strip().upper()
    if supplier_type not in SupplierDocument.ALLOWED_TYPES:
        raise ValidationError("Invalid supplier type.")
    return supplier_type


def validate_preferred_payment_method(value) -> str | None:
    method = (str(value).strip().upper() if value not in (None, "") else "")
    if not method:
        return None
    if method not in PREFERRED_METHODS:
        raise ValidationError("Invalid preferred payment method.")
    return method


def validate_status(value: str) -> str:
    status = (value or "").strip().upper()
    if status not in {item.value for item in RecordStatus}:
        raise ValidationError("Invalid status.")
    return status


def normalize_email(value: str | None) -> str | None:
    email = (value or "").strip().lower()
    return email or None


def split_list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def join_list(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value if item)


def parse_optional_int(value, *, field: str):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError(f"Invalid {field.replace('_', ' ')}.") from extra
    if number < 0:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return number


def clean_info(supplier_type: str, payload: dict | None) -> dict | None:
    if not payload or not isinstance(payload, dict):
        return None
    from apps.suppliers.constants import INFO_FIELDS

    allowed = INFO_FIELDS.get(supplier_type, ())
    cleaned = {}
    for key in allowed:
        if key not in payload:
            continue
        raw = payload.get(key)
        if key in LIST_INFO_FIELDS:
            cleaned[key] = split_list(raw)
        elif key in INT_INFO_FIELDS:
            cleaned[key] = parse_optional_int(raw, field=key)
        else:
            text = (str(raw).strip() if raw is not None else "") or None
            cleaned[key] = text
    return cleaned or None
