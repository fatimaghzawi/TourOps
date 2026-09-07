from __future__ import annotations

from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.suppliers.constants import DEFAULT_KIND_BY_SUPPLIER, KIND_LABELS, TYPE_LABELS
from apps.suppliers.offering_repositories import SupplierOfferingRepository
from core.constants import Collections, DEFAULT_CURRENCY, RecordStatus, SupplierServiceKind
from core.costing import BASIS_LABELS, parse_cost_basis
from core.exceptions import DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.numbering import next_number
from core.utils import parse_object_id, serialize_id, utcnow


def _blank(value) -> str | None:
    text = (str(value).strip() if value is not None else "") or None
    return text


def validate_kind(value: str) -> str:
    kind = (value or "").strip().upper()
    allowed = {item.value for item in SupplierServiceKind}
    if kind not in allowed:
        raise ValidationError("Invalid service type.")
    return kind


def present_offering(document: dict, *, supplier: dict | None = None) -> dict:
    cost = to_money(document.get("estimated_cost") or ZERO)
    supplier_type = (supplier or {}).get("supplier_type") or document.get("supplier_type")
    kind = document.get("service_kind") or "OTHER"
    basis = parse_cost_basis(document.get("cost_basis"), service_kind=kind)
    return {
        "id": str(document["_id"]),
        "number": document.get("service_number") or "",
        "supplier_id": serialize_id(document.get("supplier_id")),
        "supplier": (supplier or {}).get("name") or document.get("supplier_name") or "—",
        "supplier_type": supplier_type or "",
        "type_label": TYPE_LABELS.get(supplier_type, supplier_type or "Supplier"),
        "name": document.get("name") or "",
        "service_kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "description": document.get("description") or "",
        "estimated_cost": cost,
        "cost_basis": basis,
        "basis_label": BASIS_LABELS[basis],
        "currency": document.get("currency") or DEFAULT_CURRENCY,
        "notes": document.get("notes") or "",
        "status": document.get("status") or RecordStatus.ACTIVE.value,
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def serialize_offering(presented: dict) -> dict:
    payload = dict(presented)
    if isinstance(payload.get("estimated_cost"), Decimal):
        payload["estimated_cost"] = str(to_money(payload["estimated_cost"]))
    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return payload


def snapshot_offering(offering: dict, supplier: dict | None = None) -> dict:
    name = offering.get("name") or ""
    supplier_id = offering.get("supplier_id") or (supplier or {}).get("_id")
    if not supplier_id:
        raise ValidationError("A supplier service must belong to a supplier.")
    return {
        "supplier_service_id": offering["_id"],
        "supplier_id": supplier_id,
        "supplier_name": (supplier or {}).get("name") or offering.get("supplier_name") or "",
        "supplier_type": (supplier or {}).get("supplier_type") or offering.get("supplier_type"),
        "name": name,
        "description": offering.get("description") or name,
        "estimated_cost": offering.get("estimated_cost"),
        "cost_basis": parse_cost_basis(offering.get("cost_basis"), service_kind=offering.get("service_kind")),
        "service_kind": offering.get("service_kind"),
    }


class SupplierOfferingService:
    def __init__(self, repository: SupplierOfferingRepository | None = None):
        self.repository = repository or SupplierOfferingRepository()

    def list_for_supplier(self, supplier_id, *, status: str | None = None) -> list[dict]:
        supplier = self._require_supplier(supplier_id)
        extra = {"supplier_id": supplier["_id"]}
        if status:
            extra["status"] = status
        rows = []
        for document in self.repository.list_offerings(extra):
            row = present_offering(document, supplier=supplier)
            row["in_use"] = bool(
                self.repository.count_package_refs(document["_id"]) or self.repository.count_tour_refs(document["_id"])
            )
            rows.append(row)
        return rows

    def list_catalog(self, *, status: str | None = RecordStatus.ACTIVE.value, q: str | None = None) -> list[dict]:
        extra = {}
        if status:
            extra["status"] = status
        rows = []
        needle = (q or "").strip().lower()
        for document in self.repository.list_offerings(extra or None):
            supplier = None
            if document.get("supplier_id"):
                supplier = self.repository.find_supplier(document["supplier_id"])
            if status == RecordStatus.ACTIVE.value:
                if not supplier or supplier.get("status") != RecordStatus.ACTIVE.value:
                    continue
            presented = present_offering(document, supplier=supplier)
            if needle:
                hay = " ".join(
                    part
                    for part in (presented["name"], presented["supplier"], presented["kind_label"], presented["description"])
                    if part
                ).lower()
                if needle not in hay:
                    continue
            rows.append(presented)
        return rows

    def get(self, offering_id) -> dict:
        try:
            document = self.repository.find_by_id(offering_id)
        except ValidationError as extra:
            raise NotFoundError("Supplier service not found.") from extra
        if not document:
            raise NotFoundError("Supplier service not found.")
        return document

    def get_presented(self, offering_id) -> dict:
        document = self.get(offering_id)
        supplier = self.repository.find_supplier(document["supplier_id"]) if document.get("supplier_id") else None
        return present_offering(document, supplier=supplier)

    def create(self, *, actor_id, supplier_id, name: str, service_kind: str | None = None, **fields) -> dict:
        supplier = self._require_supplier(supplier_id)
        if supplier.get("status") != RecordStatus.ACTIVE.value:
            raise ValidationError("Cannot add a service to an inactive supplier.")
        document = self._document(supplier=supplier, name=name, service_kind=service_kind, existing=None, **fields)
        now = utcnow()
        document.update(
            {
                "service_number": next_number(Collections.SUPPLIER_SERVICES),
                "created_by": parse_object_id(actor_id, field="created_by"),
                "created_at": now,
                "updated_at": now,
                "status": RecordStatus.ACTIVE.value,
            }
        )
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A service with this name already exists for this supplier.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the supplier service.") from extra
        document["_id"] = result.inserted_id
        return self.get(document["_id"])

    def update(self, offering_id, *, actor_id=None, **fields) -> dict:
        existing = self.get(offering_id)
        supplier = self._require_supplier(existing["supplier_id"])
        payload = dict(fields)
        name = payload.pop("name", existing.get("name"))
        service_kind = payload.pop("service_kind", existing.get("service_kind"))
        status = payload.pop("status", None)
        updates = self._document(
            supplier=supplier,
            name=name,
            service_kind=service_kind,
            existing=existing,
            **payload,
        )
        if status is not None:
            from apps.suppliers.validators import validate_status

            updates["status"] = validate_status(status)
        updates["updated_at"] = utcnow()
        if actor_id:
            updates["updated_by"] = parse_object_id(actor_id, field="updated_by")
        try:
            self.repository.update(existing["_id"], updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not update the supplier service.") from extra
        return self.get(existing["_id"])

    def set_status(self, offering_id, status: str, *, actor_id=None) -> dict:
        return self.update(offering_id, actor_id=actor_id, status=status)

    def soft_delete(self, offering_id, *, actor_id) -> None:
        document = self.get(offering_id)
        if self.repository.count_package_refs(document["_id"]) or self.repository.count_tour_refs(document["_id"]):
            raise ValidationError("This service is used by a package or tour. Deactivate it instead of deleting.")
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not delete the supplier service.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Supplier service not found.")

    def snapshot(self, offering_id, *, require_active: bool = True) -> dict:
        offering = self.get(offering_id)
        if not offering.get("supplier_id"):
            raise ValidationError("This service is not attached to a supplier.")
        supplier = self.repository.find_supplier(offering.get("supplier_id"))
        if require_active:
            if offering.get("status") != RecordStatus.ACTIVE.value:
                raise ValidationError(f"{offering.get('name') or 'This service'} is inactive.")
            if not supplier or supplier.get("status") != RecordStatus.ACTIVE.value:
                raise ValidationError("This supplier is inactive.")
        return snapshot_offering(offering, supplier)

    def _require_supplier(self, supplier_id) -> dict:
        try:
            supplier = self.repository.find_supplier(supplier_id)
        except ValidationError as extra:
            raise NotFoundError("Supplier not found.") from extra
        if not supplier:
            raise NotFoundError("Supplier not found.")
        return supplier

    def _document(self, *, supplier, name, service_kind, existing, **fields) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Service name is required.")
        kind = validate_kind(service_kind or DEFAULT_KIND_BY_SUPPLIER.get(supplier.get("supplier_type"), "OTHER"))
        exclude = (existing or {}).get("_id")
        duplicate = self.repository.find_duplicate_name(supplier["_id"], name, exclude_id=exclude)
        if duplicate:
            raise ValidationError("This supplier already has a service with that name.")
        cost_raw = fields["estimated_cost"] if "estimated_cost" in fields else (existing or {}).get("estimated_cost", ZERO)
        if cost_raw in (None, ""):
            cost = ZERO
        else:
            cost = to_money(cost_raw)
            if cost < ZERO:
                raise ValidationError("Estimated cost cannot be negative.")
        currency = (fields.get("currency") if "currency" in fields else (existing or {}).get("currency")) or DEFAULT_CURRENCY
        currency = str(currency).strip().upper()
        if len(currency) != 3:
            raise ValidationError("Currency must be a 3-letter code.")
        basis_raw = fields["cost_basis"] if "cost_basis" in fields else (existing or {}).get("cost_basis")
        return {
            "supplier_id": supplier["_id"],
            "supplier_type": supplier.get("supplier_type"),
            "name": name,
            "name_key": name.casefold(),
            "service_kind": kind,
            "description": _blank(fields.get("description") if "description" in fields else (existing or {}).get("description")),
            "estimated_cost": to_decimal128(cost),
            "cost_basis": parse_cost_basis(basis_raw, service_kind=kind, strict="cost_basis" in fields),
            "currency": currency,
            "notes": _blank(fields.get("notes") if "notes" in fields else (existing or {}).get("notes")),
        }
