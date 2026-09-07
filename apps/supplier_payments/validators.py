from apps.supplier_payments.constants import ALLOWED_METHODS
from core.exceptions import ValidationError


def validate_payment_method(value: str) -> str:
    method = (value or "").strip().upper()
    if method not in ALLOWED_METHODS:
        raise ValidationError("Invalid payment method.")
    return method
