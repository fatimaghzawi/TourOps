from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone

from apps.expenses.validators import parse_when
from core.exceptions import ValidationError
from core.utils import parse_object_id


def parse_month(value: str | None) -> tuple[datetime, datetime] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        year_s, month_s = raw.split("-", 1)
        year, month = int(year_s), int(month_s)
        datetime(year, month, 1, tzinfo=timezone.utc)
    except (TypeError, ValueError) as extra:
        raise ValidationError("Invalid month. Use YYYY-MM.") from extra
    last = monthrange(year, month)[1]
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, last, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def parse_range(*, month: str | None = None, date_from=None, date_to=None) -> tuple[datetime | None, datetime | None]:
    start = parse_when(date_from, field="from", required=False) if date_from not in (None, "") else None
    end = parse_when(date_to, field="to", required=False) if date_to not in (None, "") else None
    if start and end and end < start:
        raise ValidationError("The end date must be on or after the start date.")
    if end and end.hour == 0 and end.minute == 0 and end.second == 0:
        end = end.replace(hour=23, minute=59, second=59)
    if start is None and end is None:
        month_range = parse_month(month)
        if month_range:
            return month_range
    return start, end


def as_aware(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return None


def in_range(value, start: datetime | None, end: datetime | None) -> bool:
    if start is None and end is None:
        return True
    when = as_aware(value)
    if when is None:
        return False
    if start and when < start:
        return False
    if end and when > end:
        return False
    return True


def parse_optional_id(value, *, field: str = "id"):
    if value in (None, ""):
        return None
    return parse_object_id(value, field=field)
