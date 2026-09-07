from __future__ import annotations

from core.constants import SupplierReservationStatus, SupplierType
from core.exceptions import ValidationError


def validate_status(value: str) -> str:
    status = (value or "").strip().upper()
    if status not in {item.value for item in SupplierReservationStatus}:
        raise ValidationError("Invalid reservation status.")
    return status


def validate_service_type(value: str) -> str:
    service_type = (value or "").strip().upper()
    if service_type not in {item.value for item in SupplierType}:
        raise ValidationError("Invalid service type.")
    return service_type
