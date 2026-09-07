from __future__ import annotations

from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.expenses.services import present_expense
from apps.suppliers.constants import DIRECTORY_TYPES, PREFERRED_METHOD_LABELS, TYPE_LABELS
from apps.suppliers.repositories import SupplierRepository
from apps.suppliers.schemas import SupplierDocument
from apps.suppliers.validators import (
    clean_info,
    join_list,
    normalize_email,
    validate_preferred_payment_method,
    validate_status,
    validate_type,
)
from core.constants import Collections, PaymentMethod, RecordStatus, SupplierType
from core.exceptions import DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_money
from core.numbering import next_number
from core.utils import parse_object_id, serialize_id, utcnow


def _blank(value) -> str | None:
    text = (str(value).strip() if value is not None else "") or None
    return text


def present_supplier(document: dict, *, owed=None, expenses=None, tours=None) -> dict:
    address = document.get("address") or {}
    bank = document.get("bank_details") or {}
    supplier_type = document.get("supplier_type")
    info_field = SupplierDocument.TYPE_INFO_FIELD.get(supplier_type)
    info = document.get(info_field) or {} if info_field else {}
    preferred_method = document.get("preferred_payment_method") or ""
    bank_parts = (
        bank.get("bank_name"),
        bank.get("account_name"),
        bank.get("iban"),
        bank.get("swift_bic"),
        bank.get("account_number"),
    )
    has_bank_details = any(bank_parts)
    bank_label = " · ".join(part for part in (bank.get("bank_name"), bank.get("iban")) if part) or "—"
    remaining = to_money(owed if owed is not None else ZERO)
    presented = {
        "id": str(document["_id"]),
        "number": document.get("supplier_number") or "",
        "name": document.get("name") or "",
        "type": supplier_type,
        "supplier_type": supplier_type,
        "type_label": TYPE_LABELS.get(supplier_type, supplier_type or ""),
        "contact": document.get("contact_person") or "",
        "contact_person": document.get("contact_person") or "",
        "phone": document.get("phone") or "",
        "email": document.get("email") or "",
        "city": address.get("city") or "",
        "country": address.get("country") or "",
        "street": address.get("street") or "",
        "address": address,
        "tax_number": document.get("tax_number") or "",
        "terms": document.get("payment_terms") or "",
        "payment_terms": document.get("payment_terms") or "",
        "preferred_payment_method": preferred_method,
        "preferred_method_label": PREFERRED_METHOD_LABELS.get(preferred_method, ""),
        "prefers_bank_transfer": preferred_method == PaymentMethod.BANK_TRANSFER.value,
        "prefers_card": preferred_method == PaymentMethod.CARD.value,
        "has_bank_details": has_bank_details,
        "bank": bank_label,
        "bank_details": bank,
        "notes": document.get("notes") or "",
        "status": document.get("status") or RecordStatus.ACTIVE.value,
        "owed": remaining,
        "has_balance": remaining > ZERO,
        "initial": (document.get("name") or "S")[:1].upper(),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "created_by": serialize_id(document.get("created_by")),
        "open_expenses": expenses or [],
        "tours": tours or [],
    }
    if supplier_type == SupplierType.HOTEL.value:
        presented.update({"stars": info.get("star_rating") or "—"})
    elif supplier_type == SupplierType.TRANSPORTATION.value:
        presented.update(
            {
                "vehicle": info.get("vehicle_type") or "—",
                "fleet": info.get("fleet_size") or "—",
                "seats": info.get("seats_per_vehicle") or "—",
                "license_number": info.get("license_number") or "",
                "coverage_areas": join_list(info.get("coverage_areas")),
            }
        )
    elif supplier_type == SupplierType.TOUR_GUIDE.value:
        presented.update(
            {
                "languages": join_list(info.get("languages")) or "—",
                "years": info.get("years_experience") or "—",
                "specialties": join_list(info.get("specialties")) or "—",
                "license_number": info.get("license_number") or "",
            }
        )
    elif supplier_type == SupplierType.AIRLINE.value:
        presented.update({"iata_code": info.get("iata_code") or "", "alliance": info.get("alliance") or ""})
    elif supplier_type == SupplierType.ACTIVITY_PROVIDER.value:
        presented.update(
            {
                "activity_kinds": join_list(info.get("activity_kinds")),
                "typical_duration_hours": info.get("typical_duration_hours") or "—",
                "location": info.get("location") or "",
            }
        )
    elif supplier_type == SupplierType.RESTAURANT.value:
        presented.update(
            {
                "cuisine": info.get("cuisine") or "",
                "seating_capacity": info.get("seating_capacity") or "—",
                "meal_types": join_list(info.get("meal_types")),
            }
        )
    elif supplier_type == SupplierType.INSURANCE.value:
        presented.update(
            {
                "policy_types": join_list(info.get("policy_types")),
                "coverage_notes": info.get("coverage_notes") or "",
            }
        )
    else:
        presented["details"] = info.get("details") or ""
    presented["info"] = info
    return presented


def serialize_supplier(presented: dict) -> dict:
    payload = dict(presented)
    if isinstance(payload.get("owed"), Decimal):
        payload["owed"] = str(to_money(payload["owed"]))
    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if hasattr(value, "isoformat") else value
    expenses = []
    for item in payload.get("open_expenses") or []:
        row = dict(item)
        for money_key in ("amount", "paid", "remaining"):
            if isinstance(row.get(money_key), Decimal):
                row[money_key] = str(to_money(row[money_key]))
        expenses.append(row)
    payload["open_expenses"] = expenses
    payload["tours"] = [
        {"id": row.get("id") or str(row.get("_id")), "name": row.get("name"), "code": row.get("tour_code") or row.get("code")}
        if isinstance(row, dict)
        else row
        for row in payload.get("tours") or []
    ]
    return payload


class SupplierService:
    def __init__(self, repository: SupplierRepository | None = None):
        self.repository = repository or SupplierRepository()

    def list_items(self, *, supplier_type: str | None = None, group: str | None = None, status: str | None = None) -> list[dict]:
        extra = {}
        if supplier_type:
            extra["supplier_type"] = validate_type(supplier_type)
        if status:
            extra["status"] = validate_status(status)
        documents = self.repository.list_suppliers(extra or None)
        if group:
            types = DIRECTORY_TYPES.get((group or "").strip().upper())
            if not types:
                raise ValidationError("Invalid supplier group.")
            documents = [doc for doc in documents if doc.get("supplier_type") in types]
        return documents

    def list_presented(self, **filters) -> list[dict]:
        owed = self.repository.remaining_by_supplier()
        return [present_supplier(doc, owed=owed.get(str(doc["_id"]), ZERO)) for doc in self.list_items(**filters)]

    def get(self, supplier_id) -> dict:
        try:
            document = self.repository.find_by_id(supplier_id)
        except ValidationError as extra:
            raise NotFoundError("Supplier not found.") from extra
        if not document:
            raise NotFoundError("Supplier not found.")
        return document

    def get_presented(self, supplier_id, *, include_extras: bool = True) -> dict:
        document = self.get(supplier_id)
        expenses = None
        tours = None
        owed = None
        if include_extras:
            raw_expenses = self.repository.list_expenses_for(document["_id"])
            presented_expenses = []
            total = ZERO
            for expense in raw_expenses:
                row = present_expense(expense)
                total += to_money(row["remaining"])
                if row["has_remaining"]:
                    presented_expenses.append(row)
            expenses = presented_expenses
            owed = total
            tours = [
                {
                    "id": str(tour["_id"]),
                    "name": tour.get("name") or tour.get("tour_code") or "Tour",
                    "code": tour.get("tour_code") or "",
                }
                for tour in self.repository.list_tours_for(document["_id"])
            ]
        else:
            owed_map = self.repository.remaining_by_supplier()
            owed = owed_map.get(str(document["_id"]), ZERO)
        return present_supplier(document, owed=owed, expenses=expenses, tours=tours)

    def create(self, *, actor_id, name: str, supplier_type: str, **fields) -> dict:
        document = self._document(name=name, supplier_type=supplier_type, actor_id=actor_id, existing=None, **fields)
        now = utcnow()
        document.update(
            {
                "supplier_number": next_number(Collections.SUPPLIERS),
                "created_by": parse_object_id(actor_id, field="created_by"),
                "created_at": now,
                "updated_at": now,
                "status": RecordStatus.ACTIVE.value,
            }
        )
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A supplier with this number already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the supplier.") from extra
        document["_id"] = result.inserted_id
        return self.get(document["_id"])

    def update(self, supplier_id, *, actor_id=None, **fields) -> dict:
        existing = self.get(supplier_id)
        fields = dict(fields)
        name = fields.pop("name", existing.get("name"))
        supplier_type = (
            fields.pop("supplier_type", None) or fields.pop("type", None) or existing.get("supplier_type")
        )
        updates = self._document(
            name=name,
            supplier_type=supplier_type,
            actor_id=actor_id,
            existing=existing,
            **fields,
        )
        if "status" in fields and fields["status"] is not None:
            updates["status"] = validate_status(fields["status"])
        updates["updated_at"] = utcnow()
        try:
            self.repository.update(existing["_id"], updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not update the supplier.") from extra
        return self.get(existing["_id"])

    def set_status(self, supplier_id, status: str, *, actor_id=None) -> dict:
        return self.update(supplier_id, actor_id=actor_id, status=status)

    def soft_delete(self, supplier_id, *, actor_id) -> None:
        presented = self.get_presented(supplier_id)
        if presented["has_balance"]:
            raise ValidationError("Cannot delete a supplier with an outstanding balance.")
        from apps.suppliers.offerings import SupplierOfferingService

        if SupplierOfferingService().repository.count_supplier_product_refs(presented["id"]):
            raise ValidationError("This supplier is used by a package or tour. Deactivate it instead of deleting.")
        try:
            result = self.repository.soft_delete(presented["id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not delete the supplier.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Supplier not found.")

    def _document(self, *, name, supplier_type, actor_id, existing, **fields) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Supplier name is required.")
        supplier_type = validate_type(supplier_type)

        def scalar(key, alias=None, nested=None):
            if key in fields:
                return fields[key]
            if alias and alias in fields:
                return fields[alias]
            if nested and isinstance(fields.get(nested), dict) and key in fields[nested]:
                return fields[nested][key]
            if existing:
                if nested:
                    return (existing.get(nested) or {}).get(key)
                return existing.get(key)
            return None

        address = {
            "country": _blank(scalar("country", nested="address")) or "",
            "city": _blank(scalar("city", nested="address")) or "",
            "street": _blank(scalar("street", nested="address")),
        }
        preferred_method = validate_preferred_payment_method(scalar("preferred_payment_method"))
        bank_keys = ("bank_name", "account_name", "iban", "swift_bic", "account_number")
        existing_bank = dict((existing or {}).get("bank_details") or {})
        bank_details = {key: existing_bank.get(key) for key in bank_keys}

        def _incoming_bank(key: str) -> bool:
            if key in fields:
                return True
            nested = fields.get("bank_details")
            return isinstance(nested, dict) and key in nested

        if any(_incoming_bank(key) for key in bank_keys):
            for key in bank_keys:
                if _incoming_bank(key):
                    bank_details[key] = _blank(scalar(key, nested="bank_details"))
        info_key = SupplierDocument.TYPE_INFO_FIELD[supplier_type]
        previous = (existing or {}).get(info_key) or {} if existing and existing.get("supplier_type") == supplier_type else {}
        incoming = fields.get(info_key) if isinstance(fields.get(info_key), dict) else fields
        info = clean_info(supplier_type, {**previous, **(incoming or {})})
        document = {
            "name": name,
            "supplier_type": supplier_type,
            "contact_person": _blank(scalar("contact_person", alias="contact")),
            "email": normalize_email(scalar("email")),
            "phone": _blank(scalar("phone")),
            "address": address,
            "tax_number": _blank(scalar("tax_number")),
            "payment_terms": _blank(scalar("payment_terms", alias="terms")),
            "preferred_payment_method": preferred_method,
            "bank_details": bank_details,
            "notes": _blank(scalar("notes")),
        }
        for field_name in SupplierDocument.TYPE_INFO_FIELD.values():
            document[field_name] = info if field_name == info_key else None
        return document
