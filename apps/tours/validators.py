from __future__ import annotations

from datetime import timedelta

from core.constants import TourStatus
from core.exceptions import ValidationError
from apps.tours.schemas import available_seats


def validate_tour_status(value: str) -> str:
    status = (value or "").strip().upper()
    if status not in {item.value for item in TourStatus}:
        raise ValidationError("Invalid tour status.")
    return status


def seat_status(status: str, *, capacity: int, booked: int) -> str:
    current = validate_tour_status(status) if status else TourStatus.AVAILABLE.value
    locked = {TourStatus.CANCELLED.value, TourStatus.COMPLETED.value, TourStatus.DRAFT.value, TourStatus.IN_PROGRESS.value}
    if current in locked:
        return current
    if available_seats(capacity, booked) == 0 and capacity > 0:
        return TourStatus.FULLY_BOOKED.value
    if current == TourStatus.FULLY_BOOKED.value:
        return TourStatus.AVAILABLE.value
    return current


def default_end(start, duration_days):
    if not start or not duration_days:
        return None
    days = int(duration_days)
    return start + timedelta(days=max(days - 1, 0))


def ensure_date_order(start, end) -> None:
    if start and end and end < start:
        raise ValidationError("End date cannot be before start date.")
