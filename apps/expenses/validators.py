from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from core.constants import ExpenseCategory, ExpensePaymentStatus, ExpenseScope
from core.exceptions import ValidationError
from core.money import ZERO, to_money
from core.utils import parse_object_id


def _coerce_money(value, *, field: str) -> Decimal:
    if isinstance(value, float):
        value = format(value, ".2f")
    try:
        return to_money(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid {field}.") from exc


def parse_positive_money(value, *, field: str = "amount") -> Decimal:
    amount = _coerce_money(value, field=field)
    if amount <= ZERO:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} must be greater than zero.")
    return amount


def parse_money(value, *, field: str = "amount") -> Decimal:
    amount = _coerce_money(value, field=field)
    if amount < ZERO:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return amount


def parse_optional_object_id(value, *, field: str):
    if value in (None, ""):
        return None
    return parse_object_id(value, field=field)


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
    except ValueError as exc:
        raise ValidationError(f"Invalid {field}. Use YYYY-MM-DD.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_scope(scope: str) -> str:
    value = (scope or "").strip().upper()
    if value not in {item.value for item in ExpenseScope}:
        raise ValidationError("Invalid expense scope.")
    return value


def validate_category(category: str) -> str:
    value = (category or "").strip().upper()
    if value not in {item.value for item in ExpenseCategory}:
        raise ValidationError("Invalid expense category.")
    return value


def payment_status_for(amount: Decimal, paid: Decimal) -> str:
    if paid <= ZERO:
        return ExpensePaymentStatus.UNPAID.value
    if paid >= amount:
        return ExpensePaymentStatus.PAID.value
    return ExpensePaymentStatus.PARTIALLY_PAID.value


def remaining_for(amount: Decimal, paid: Decimal) -> Decimal:
    remaining = to_money(amount - paid)
    if remaining < ZERO:
        raise ValidationError("Paid amount cannot exceed the expense total.")
    return remaining
