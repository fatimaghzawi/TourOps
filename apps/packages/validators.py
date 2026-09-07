from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from core.constants import DEFAULT_CURRENCY, PackageStatus
from core.exceptions import TourOpsError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.utils import parse_object_id


def split_list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\r\n", "\n")
    if "\n" in text:
        return [part.strip() for part in text.split("\n") if part.strip()]
    return [part.strip() for part in text.split(",") if part.strip()]


def join_list(value, *, sep: str = ", ") -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return sep.join(str(item) for item in value if item)


def duration_label(days) -> str:
    try:
        count = int(days or 0)
    except (TypeError, ValueError):
        return "—"
    if count <= 0:
        return "—"
    nights = max(count - 1, 0)
    if count == 1:
        return "1 day"
    night_word = "night" if nights == 1 else "nights"
    return f"{count} days / {nights} {night_word}"


def format_dates(start, end) -> str:
    start_day = _as_date(start)
    end_day = _as_date(end)
    if not start_day:
        return "—"
    if not end_day:
        return start_day.strftime("%d %b %Y")
    if start_day.year == end_day.year and start_day.month == end_day.month:
        return f"{start_day.day}–{end_day.day} {end_day.strftime('%b %Y')}"
    if start_day.year == end_day.year:
        return f"{start_day.day} {start_day.strftime('%b')}–{end_day.day} {end_day.strftime('%b %Y')}"
    return f"{start_day.strftime('%d %b %Y')} – {end_day.strftime('%d %b %Y')}"


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_when(value, *, field: str, required: bool = True) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required.")
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(raw.replace("Z", "+0000") if fmt.endswith("%z") else raw, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as extra:
        raise ValidationError(f"Invalid {field}. Use YYYY-MM-DD.") from extra
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_positive_int(value, *, field: str) -> int:
    if value in (None, ""):
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required.")
    try:
        number = int(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError(f"Invalid {field.replace('_', ' ')}.") from extra
    if number < 1:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} must be at least 1.")
    return number


def parse_non_negative_int(value, *, field: str, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError(f"Invalid {field.replace('_', ' ')}.") from extra
    if number < 0:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return number


def parse_price(value, *, field: str = "price") -> Decimal:
    if isinstance(value, float):
        value = format(value, ".2f")
    try:
        amount = to_money(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError(f"Invalid {field}.") from extra
    if amount <= ZERO:
        raise ValidationError("Price must be greater than zero.")
    return amount


def parse_optional_money(value, *, field: str = "estimated_cost") -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, float):
        value = format(value, ".2f")
    try:
        amount = to_money(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError(f"Invalid {field}.") from extra
    if amount < ZERO:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return amount


def parse_optional_object_id(value, *, field: str):
    if value in (None, ""):
        return None
    return parse_object_id(value, field=field)


def validate_package_status(value: str) -> str:
    status = (value or "").strip().upper()
    if status not in {item.value for item in PackageStatus}:
        raise ValidationError("Invalid package status.")
    return status


def normalize_currency(value) -> str:
    currency = (str(value).strip().upper() if value not in (None, "") else DEFAULT_CURRENCY) or DEFAULT_CURRENCY
    if len(currency) != 3:
        raise ValidationError("Currency must be a 3-letter code.")
    return currency


def clean_destination(*, city, country) -> dict:
    city_text = (str(city).strip() if city not in (None, "") else "")
    country_text = (str(country).strip() if country not in (None, "") else "")
    if not city_text:
        raise ValidationError("City is required.")
    return {"country": country_text, "city": city_text}


def copy_service_lines(lines) -> list[dict]:
    copied = []
    for item in lines or []:
        if not isinstance(item, dict):
            continue
        copied.append(
            {
                "supplier_service_id": item.get("supplier_service_id"),
                "supplier_id": item.get("supplier_id"),
                "supplier_name": item.get("supplier_name") or item.get("supplier") or "",
                "supplier_type": item.get("supplier_type"),
                "name": item.get("name") or item.get("description") or "",
                "description": item.get("description") or item.get("name") or "",
                "estimated_cost": item.get("estimated_cost"),
                "cost_basis": item.get("cost_basis"),
                "service_kind": item.get("service_kind"),
            }
        )
    return copied


def clean_service_lines(
    raw,
    *,
    lookup_supplier,
    lookup_offering=None,
    require_active: bool = True,
    existing_lines=None,
) -> list[dict]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValidationError("Services must be a list.")
    existing_by_id = {}
    for line in existing_lines or []:
        if not isinstance(line, dict):
            continue
        key = str(line.get("supplier_service_id") or "")
        if key:
            existing_by_id[key] = line
    lines = []
    seen = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"Service {index} is invalid.")
        offering_id = parse_optional_object_id(item.get("supplier_service_id"), field="supplier_service_id")
        if offering_id:
            if lookup_offering is None:
                raise ValidationError("Supplier services catalog is unavailable.")
            key = str(offering_id)
            if key in existing_by_id:
                if key in seen:
                    raise ValidationError("The same supplier service cannot be added twice.")
                seen.add(key)
                lines.append(copy_service_lines([existing_by_id[key]])[0])
                continue
            try:
                snapshot = lookup_offering(offering_id, require_active=require_active)
            except TourOpsError as extra:
                raise ValidationError(f"Service {index}: {extra.message}") from extra
            key = str(snapshot.get("supplier_service_id") or offering_id)
            if key in seen:
                raise ValidationError("The same supplier service cannot be added twice.")
            seen.add(key)
            lines.append(snapshot)
            continue
        supplier_id = parse_optional_object_id(item.get("supplier_id"), field="supplier_id")
        if not supplier_id:
            raise ValidationError(f"Service {index} needs a supplier service.")
        supplier = lookup_supplier(supplier_id)
        if not supplier:
            raise ValidationError(f"Service {index}: supplier not found.")
        description = (item.get("description") or item.get("name") or "").strip()
        if not description:
            raise ValidationError(f"Service {index} needs a description.")
        lines.append(
            {
                "supplier_service_id": None,
                "supplier_id": supplier_id,
                "supplier_name": supplier.get("name") or "",
                "supplier_type": supplier.get("supplier_type") or (item.get("supplier_type") or "").strip().upper(),
                "name": description,
                "description": description,
                "estimated_cost": to_decimal128(parse_optional_money(item.get("estimated_cost"))),
                "cost_basis": item.get("cost_basis"),
                "service_kind": (item.get("service_kind") or "").strip().upper() or None,
            }
        )
    return lines
