from __future__ import annotations

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.customers.repositories import CustomerRepository
from core.constants import Collections, RecordStatus
from core.exceptions import DatabaseUnavailableError, NotFoundError, ValidationError
from core.numbering import next_number
from core.utils import full_name, parse_object_id, utcnow


def _blank(value) -> str | None:
    text = (str(value).strip() if value is not None else "") or None
    return text


def present_customer(document: dict) -> dict:
    first = document.get("first_name") or ""
    last = document.get("last_name") or ""
    name = full_name(first, last) or document.get("email") or "Customer"
    parts = [part for part in (first, last) if part]
    initials = "".join(part[0] for part in parts[:2]).upper() or "C"
    address = document.get("address") or {}
    passport = document.get("passport") or {}
    return {
        "id": str(document["_id"]),
        "number": document.get("customer_number") or "",
        "customer_number": document.get("customer_number") or "",
        "first_name": first,
        "last_name": last,
        "first": first,
        "last": last,
        "name": name,
        "initials": initials,
        "email": document.get("email") or "",
        "phone": document.get("phone") or "",
        "city": address.get("city") or "",
        "country": address.get("country") or "",
        "passport": passport.get("number") or "",
        "nationality": document.get("nationality") or "",
        "status": document.get("status") or RecordStatus.ACTIVE.value,
        "notes": document.get("notes") or "",
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


class CustomerService:
    def __init__(self, repository: CustomerRepository | None = None):
        self.repository = repository or CustomerRepository()

    def list_items(self, *, query: str | None = None, status: str | None = None) -> list[dict]:
        if query or status:
            return self.repository.find_all(limit=500, query=query, status=status)
        return self.repository.list_customers()

    def list_presented(self, *, query: str | None = None, status: str | None = None) -> list[dict]:
        return [present_customer(doc) for doc in self.list_items(query=query, status=status)]

    def list_options(self) -> list[tuple[str, str]]:
        return [(row["id"], f"{row['name']} · {row['number']}") for row in self.list_presented()]

    def get(self, customer_id) -> dict:
        try:
            document = self.repository.find_by_id(customer_id)
        except ValidationError as extra:
            raise NotFoundError("Customer not found.") from extra
        if not document:
            raise NotFoundError("Customer not found.")
        return document

    def get_presented(self, customer_id) -> dict:
        return present_customer(self.get(customer_id))

    def create(self, *, actor_id, first_name: str, last_name: str, email: str, phone: str = "", **fields) -> dict:
        first = (first_name or "").strip()
        last = (last_name or "").strip()
        if not first or not last:
            raise ValidationError("First and last name are required.")
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValidationError("A valid email is required.")
        now = utcnow()
        document = {
            "customer_number": next_number(Collections.CUSTOMERS),
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": (phone or "").strip(),
            "nationality": _blank(fields.get("nationality")),
            "address": {
                "city": (fields.get("city") or "").strip(),
                "country": (fields.get("country") or "").strip(),
                "street": _blank(fields.get("street")),
            },
            "passport": {"number": _blank(fields.get("passport") or fields.get("passport_number"))},
            "notes": _blank(fields.get("notes")),
            "status": RecordStatus.ACTIVE.value,
            "created_by": parse_object_id(actor_id, field="created_by"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A customer with this email already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the customer.") from extra
        document["_id"] = result.inserted_id
        return self.get(document["_id"])

    def update(self, customer_id, *, actor_id, first_name: str, last_name: str, email: str, phone: str = "", **fields) -> dict:
        self.get(customer_id)
        first = (first_name or "").strip()
        last = (last_name or "").strip()
        if not first or not last:
            raise ValidationError("First and last name are required.")
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValidationError("A valid email is required.")
        existing = self.repository.find_by_email(email)
        if existing and str(existing["_id"]) != str(customer_id):
            raise ValidationError("A customer with this email already exists.")
        updates = {
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": (phone or "").strip(),
            "nationality": _blank(fields.get("nationality")),
            "address": {
                "city": (fields.get("city") or "").strip(),
                "country": (fields.get("country") or "").strip(),
                "street": _blank(fields.get("street")),
            },
            "passport": {"number": _blank(fields.get("passport") or fields.get("passport_number"))},
            "notes": _blank(fields.get("notes")),
            "updated_by": parse_object_id(actor_id, field="updated_by"),
            "updated_at": utcnow(),
        }
        try:
            self.repository.update(customer_id, updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the customer.") from extra
        return self.get(customer_id)
