from datetime import datetime
from email.utils import parseaddr


def validate_customer_data(data: dict, partial: bool = False):
    errors = {}

    required_fields = ["first_name", "last_name", "email", "phone"]

    if not partial:
        for field in required_fields:
            if not data.get(field):
                errors[field] = f"{field} is required."

    if "email" in data and data["email"]:
        email = str(data["email"]).strip()
        parsed_email = parseaddr(email)[1]

        if not parsed_email or "@" not in parsed_email:
            errors["email"] = "Invalid email format."

    if "date_of_birth" in data and data["date_of_birth"]:
        try:
            datetime.fromisoformat(str(data["date_of_birth"]))
        except ValueError:
            errors["date_of_birth"] = "Invalid date format. Use ISO-8601."

    for field in ["address", "passport", "emergency_contact"]:
        if field in data and data[field] is not None:
            if not isinstance(data[field], dict):
                errors[field] = f"{field} must be an object."

    if errors:
        return False, errors

    return True, None