from __future__ import annotations

from decimal import Decimal

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from core.constants import (
    Collections,
    DEFAULT_CURRENCY,
    DEFAULT_TAX_NAME,
    NUMBER_PREFIXES,
    NUMBER_START,
)
from core.database import get_collection
from core.exceptions import DatabaseUnavailableError, ValidationError
from core.money import ZERO, to_money
from core.utils import parse_object_id, utcnow

SETTINGS_ID = "agency"
SETTINGS_AUDIT_ID = ObjectId("0000000000000000000000aa")

PREFIX_LABELS = {
    Collections.CUSTOMERS: "Customer",
    Collections.SUPPLIERS: "Supplier",
    Collections.TOURS: "Tour",
    Collections.PACKAGES: "Package",
    Collections.BOOKINGS: "Booking",
    Collections.INVOICES: "Invoice",
    Collections.PAYMENTS: "Payment",
    Collections.RECEIPTS: "Receipt",
    Collections.REFUNDS: "Refund",
    Collections.EXPENSES: "Expense",
    Collections.SUPPLIER_PAYMENTS: "Supplier payment",
    Collections.SUPPLIER_RESERVATIONS: "Supplier reservation",
    Collections.SUPPLIER_SERVICES: "Supplier service",
}

PREFIX_SPECS = tuple(
    (key, PREFIX_LABELS.get(key, key.replace("_", " ").title()), NUMBER_PREFIXES[key])
    for key in NUMBER_PREFIXES
)


def _default_prefixes() -> dict[str, str]:
    return {key: value for key, value in NUMBER_PREFIXES.items()}


def default_settings() -> dict:
    return {
        "agency": {
            "name": "TourOps",
            "legal_name": "",
            "email": "",
            "phone": "",
            "address": "",
        },
        "currency": DEFAULT_CURRENCY,
        "tax_name": DEFAULT_TAX_NAME,
        "tax_rate": "0.00",
        "tax_enabled": True,
        "invoice_due_days": 14,
        "number_start": NUMBER_START,
        "prefixes": _default_prefixes(),
        "prefix_rows": [(label, NUMBER_PREFIXES[key]) for key, label, _default in PREFIX_SPECS],
    }


def present_settings(document: dict | None) -> dict:
    base = default_settings()
    if not document:
        return base
    agency = document.get("agency") or {}
    prefixes = dict(base["prefixes"])
    saved_prefixes = document.get("prefixes") or {}
    for key in prefixes:
        value = (saved_prefixes.get(key) or "").strip().upper()
        if value:
            prefixes[key] = value
    tax_rate = to_money(document.get("tax_rate", ZERO))
    number_start = int(document.get("number_start") or NUMBER_START)
    due_days = int(document.get("invoice_due_days") or 14)
    presented = {
        "agency": {
            "name": (agency.get("name") or base["agency"]["name"]).strip() or base["agency"]["name"],
            "legal_name": (agency.get("legal_name") or "").strip(),
            "email": (agency.get("email") or "").strip(),
            "phone": (agency.get("phone") or "").strip(),
            "address": (agency.get("address") or "").strip(),
        },
        "currency": ((document.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY),
        "tax_name": ((document.get("tax_name") or DEFAULT_TAX_NAME).strip() or DEFAULT_TAX_NAME),
        "tax_rate": str(tax_rate),
        "tax_enabled": bool(document.get("tax_enabled", True)),
        "invoice_due_days": due_days,
        "number_start": number_start,
        "prefixes": prefixes,
        "prefix_rows": [(PREFIX_LABELS.get(key, key), prefixes[key]) for key, _label, _default in PREFIX_SPECS],
    }
    return presented


class SettingsService:
    def __init__(self):
        self.collection = get_collection(Collections.SYSTEM_SETTINGS)

    def get(self) -> dict:
        try:
            document = self.collection.find_one({"_id": SETTINGS_ID})
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not load settings.") from extra
        return present_settings(document)

    def update(self, *, actor_id, **fields) -> dict:
        name = (fields.get("agency_name") or "").strip()
        if not name:
            raise ValidationError("Agency name is required.")
        currency = (fields.get("currency") or DEFAULT_CURRENCY).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationError("Currency must be a 3-letter code.")
        tax_name = (fields.get("tax_name") or DEFAULT_TAX_NAME).strip() or DEFAULT_TAX_NAME
        tax_rate = to_money(fields.get("tax_rate") or ZERO)
        if tax_rate < ZERO or tax_rate > Decimal("100"):
            raise ValidationError("Tax rate must be between 0 and 100.")
        due_days = int(fields.get("invoice_due_days") or 14)
        if due_days < 1 or due_days > 120:
            raise ValidationError("Invoice due days must be between 1 and 120.")
        number_start = int(fields.get("number_start") or NUMBER_START)
        if number_start < 1:
            raise ValidationError("Numbering must start at 1 or higher.")
        prefixes = _default_prefixes()
        incoming = fields.get("prefixes") or {}
        for key in prefixes:
            value = (incoming.get(key) or "").strip().upper()
            if value:
                prefixes[key] = value[:8]
        payload = {
            "agency": {
                "name": name,
                "legal_name": (fields.get("legal_name") or "").strip(),
                "email": (fields.get("agency_email") or "").strip().lower(),
                "phone": (fields.get("agency_phone") or "").strip(),
                "address": (fields.get("agency_address") or "").strip(),
            },
            "currency": currency,
            "tax_name": tax_name,
            "tax_rate": str(tax_rate),
            "tax_enabled": bool(fields.get("tax_enabled", True)),
            "invoice_due_days": due_days,
            "number_start": number_start,
            "prefixes": prefixes,
            "updated_at": utcnow(),
            "updated_by": parse_object_id(actor_id, field="updated_by") if actor_id else None,
        }
        try:
            self.collection.find_one_and_update(
                {"_id": SETTINGS_ID},
                {"$set": payload},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save settings.") from extra
        presented = self.get()
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.UPDATED.value,
            entity_type="system_settings",
            entity_id=SETTINGS_AUDIT_ID,
            description="Updated system settings.",
            after={"agency": presented["agency"]["name"], "currency": presented["currency"]},
        )
        return presented


def initial_from_settings(settings: dict) -> dict:
    agency = (settings or {}).get("agency") or {}
    initial = {
        "agency_name": agency.get("name") or "",
        "legal_name": agency.get("legal_name") or "",
        "agency_email": agency.get("email") or "",
        "agency_phone": agency.get("phone") or "",
        "agency_address": agency.get("address") or "",
        "currency": settings.get("currency") or DEFAULT_CURRENCY,
        "tax_name": settings.get("tax_name") or DEFAULT_TAX_NAME,
        "tax_rate": settings.get("tax_rate") or "0.00",
        "tax_enabled": bool(settings.get("tax_enabled", True)),
        "invoice_due_days": settings.get("invoice_due_days") or 14,
        "number_start": settings.get("number_start") or NUMBER_START,
    }
    for key, value in (settings.get("prefixes") or {}).items():
        initial[f"prefix_{key}"] = value
    return initial


def prefix_for(collection_name: str, fallback: str | None = None) -> str | None:
    key = getattr(collection_name, "value", collection_name)
    try:
        saved = SettingsService().get().get("prefixes") or {}
        value = (saved.get(key) or "").strip()
        if value:
            return value
    except Exception:
        pass
    if fallback:
        return fallback
    return NUMBER_PREFIXES.get(key) or NUMBER_PREFIXES.get(collection_name)


def number_start() -> int:
    try:
        value = int(SettingsService().get().get("number_start") or NUMBER_START)
        if value >= 1:
            return value
    except Exception:
        pass
    return NUMBER_START
