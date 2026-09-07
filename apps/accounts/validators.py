from apps.accounts.constants import MIN_PASSWORD_LENGTH
from core.exceptions import ValidationError


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_password(password: str) -> str:
    raw = password or ""
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return raw
