from __future__ import annotations

from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.packages.repositories import PackageRepository
from apps.packages.validators import (
    clean_destination,
    clean_service_lines,
    duration_label,
    format_dates,
    join_list,
    normalize_currency,
    parse_positive_int,
    parse_price,
    split_list,
    validate_package_status,
)
from apps.suppliers.constants import TYPE_LABELS
from core.constants import Collections, DEFAULT_CURRENCY, PackageStatus
from core.costing import BASIS_LABELS, cost_sheet, parse_cost_basis, parse_margin_percent, serialize_costing
from core.exceptions import DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.numbering import next_number
from core.utils import parse_object_id, serialize_id, utcnow


def _blank(value) -> str:
    return (str(value).strip() if value is not None else "") or ""


def present_service(line: dict, *, supplier: dict | None = None) -> dict:
    cost = to_money((line or {}).get("estimated_cost"))
    supplier_type = (supplier or {}).get("supplier_type") or (line or {}).get("supplier_type")
    title = (line or {}).get("name") or (line or {}).get("description") or (supplier or {}).get("name") or "Service"
    kind = (line or {}).get("service_kind") or ""
    basis = parse_cost_basis((line or {}).get("cost_basis"), service_kind=kind)
    return {
        "supplier_service_id": serialize_id((line or {}).get("supplier_service_id")),
        "supplier_id": serialize_id((line or {}).get("supplier_id")),
        "supplier": (supplier or {}).get("name") or (line or {}).get("supplier_name") or (line or {}).get("supplier") or "—",
        "supplier_type": supplier_type or "",
        "type_label": TYPE_LABELS.get(supplier_type, supplier_type or "Supplier"),
        "description": (line or {}).get("description") or title,
        "name": title,
        "estimated_cost": cost,
        "est": cost,
        "cost_basis": basis,
        "basis_label": BASIS_LABELS[basis],
        "title": title,
        "service_kind": kind,
    }


def present_package(document: dict, *, tours=None, services=None) -> dict:
    destination = document.get("destination") or {}
    included = document.get("included_services") or []
    excluded = document.get("excluded_services") or []
    price = to_money(document.get("selling_price_per_person"))
    days = document.get("duration_days") or 0
    capacity = document.get("default_capacity") or 0
    margin = parse_margin_percent(document.get("target_margin_percent"))
    costing = cost_sheet(
        services if services is not None else document.get("services"),
        capacity=capacity or 1,
        selling_price=price,
        margin_percent=margin,
    )
    return {
        "id": str(document["_id"]),
        "code": document.get("package_code") or "",
        "package_code": document.get("package_code") or "",
        "name": document.get("name") or "",
        "description": document.get("description") or "",
        "city": destination.get("city") or "",
        "country": destination.get("country") or "",
        "destination": destination,
        "duration": duration_label(days),
        "duration_days": days,
        "price": price,
        "selling_price_per_person": price,
        "target_margin_percent": margin,
        "costing": costing,
        "currency": document.get("currency") or DEFAULT_CURRENCY,
        "default_capacity": document.get("default_capacity") or 0,
        "includes": join_list(included, sep=" + "),
        "included_services": included,
        "excluded": join_list(excluded),
        "excluded_services": excluded,
        "status": document.get("status") or PackageStatus.ACTIVE.value,
        "services": services or [],
        "tours": tours or [],
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "created_by": serialize_id(document.get("created_by")),
    }


def serialize_package(presented: dict) -> dict:
    payload = dict(presented)
    for key in ("price", "selling_price_per_person"):
        if isinstance(payload.get(key), Decimal):
            payload[key] = str(to_money(payload[key]))
    if isinstance(payload.get("target_margin_percent"), Decimal):
        payload["target_margin_percent"] = str(to_money(payload["target_margin_percent"]))
    payload["costing"] = serialize_costing(payload.get("costing"))
    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if hasattr(value, "isoformat") else value
    services = []
    for line in payload.get("services") or []:
        row = dict(line)
        for money_key in ("estimated_cost", "est"):
            if isinstance(row.get(money_key), Decimal):
                row[money_key] = str(to_money(row[money_key]))
        services.append(row)
    payload["services"] = services
    return payload


class PackageService:
    def __init__(self, repository: PackageRepository | None = None):
        self.repository = repository or PackageRepository()

    def list_items(self, *, status: str | None = None) -> list[dict]:
        extra = {}
        if status:
            extra["status"] = validate_package_status(status)
        return self.repository.list_packages(extra or None)

    def list_presented(self, **filters) -> list[dict]:
        return [self._present(doc, include_extras=False) for doc in self.list_items(**filters)]

    def list_options(self) -> list[tuple[str, str]]:
        return [
            (str(doc["_id"]), doc.get("name") or doc.get("package_code") or "Package")
            for doc in self.list_items(status=PackageStatus.ACTIVE.value)
        ]

    def get(self, package_id) -> dict:
        try:
            document = self.repository.find_by_id(package_id)
        except ValidationError as extra:
            raise NotFoundError("Package not found.") from extra
        if not document:
            raise NotFoundError("Package not found.")
        return document

    def get_presented(self, package_id, *, include_extras: bool = True) -> dict:
        return self._present(self.get(package_id), include_extras=include_extras)

    def create(self, *, actor_id, name: str, **fields) -> dict:
        document = self._document(name=name, existing=None, **fields)
        now = utcnow()
        document.update(
            {
                "package_code": next_number(Collections.PACKAGES),
                "created_by": parse_object_id(actor_id, field="created_by"),
                "created_at": now,
                "updated_at": now,
                "status": document.get("status") or PackageStatus.ACTIVE.value,
            }
        )
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A package with this code already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the package.") from extra
        document["_id"] = result.inserted_id
        return self.get(document["_id"])

    def update(self, package_id, *, actor_id=None, **fields) -> dict:
        existing = self.get(package_id)
        updates = self._document(name=fields.get("name", existing.get("name")), existing=existing, **fields)
        if "status" in fields and fields["status"] is not None:
            updates["status"] = validate_package_status(fields["status"])
        updates["updated_at"] = utcnow()
        try:
            self.repository.update(existing["_id"], updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not update the package.") from extra
        return self.get(existing["_id"])

    def soft_delete(self, package_id, *, actor_id) -> None:
        document = self.get(package_id)
        if self.repository.count_tours(document["_id"]):
            raise ValidationError("Cannot delete a package that still has departures.")
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not delete the package.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Package not found.")

    def _present(self, document: dict, *, include_extras: bool) -> dict:
        services = [self._service(line) for line in document.get("services") or []]
        tours = None
        if include_extras:
            tours = []
            for tour in self.repository.list_tours_for(document["_id"]):
                tours.append(
                    {
                        "id": str(tour["_id"]),
                        "name": tour.get("name") or tour.get("tour_code") or "Tour",
                        "code": tour.get("tour_code") or "",
                        "dates": format_dates(tour.get("start_date"), tour.get("end_date")),
                        "status": tour.get("status"),
                    }
                )
        presented = present_package(document, tours=tours, services=services)
        if not include_extras:
            presented["services"] = []
            presented["tours"] = []
        return presented

    def _service(self, line: dict) -> dict:
        supplier = None
        if line.get("supplier_id"):
            try:
                supplier = self.repository.find_supplier(line["supplier_id"])
            except ValidationError:
                supplier = None
        hydrated = dict(line)
        hydrated["estimated_cost"] = to_money(line.get("estimated_cost"))
        return present_service(hydrated, supplier=supplier)

    def _lookup_supplier(self, supplier_id):
        return self.repository.find_supplier(supplier_id)

    def _lookup_offering(self, offering_id, *, require_active: bool = True) -> dict:
        from apps.suppliers.offerings import SupplierOfferingService

        return SupplierOfferingService().snapshot(offering_id, require_active=require_active)

    def _document(self, *, name, existing, **fields) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Package name is required.")

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

        destination = clean_destination(city=scalar("city", nested="destination"), country=scalar("country", nested="destination"))
        duration_raw = scalar("duration_days")
        if duration_raw is None and existing is None:
            raise ValidationError("Duration is required.")
        duration_days = parse_positive_int(duration_raw if duration_raw is not None else existing.get("duration_days"), field="duration_days")
        capacity_raw = scalar("default_capacity")
        default_capacity = parse_positive_int(
            capacity_raw if capacity_raw is not None else (existing.get("default_capacity") if existing else 1),
            field="default_capacity",
        )
        margin = parse_margin_percent(scalar("target_margin_percent"))
        if "services" in fields:
            services = clean_service_lines(
                fields.get("services"),
                lookup_supplier=self._lookup_supplier,
                lookup_offering=self._lookup_offering,
                require_active=True,
                existing_lines=(existing or {}).get("services"),
            )
        else:
            services = list((existing or {}).get("services") or [])
        price_raw = scalar("selling_price_per_person", alias="price")
        if price_raw in (None, ""):
            if existing:
                price = parse_price(existing.get("selling_price_per_person"))
            else:
                suggested = cost_sheet(services, capacity=default_capacity, margin_percent=margin)["suggested_price"]
                if suggested <= ZERO:
                    raise ValidationError("Set a selling price, or add supplier costs so one can be calculated.")
                price = suggested
        else:
            price = parse_price(price_raw)
        if "included_services" in fields or "includes" in fields:
            included = split_list(fields.get("included_services", fields.get("includes")))
        else:
            included = list((existing or {}).get("included_services") or [])
        if "excluded_services" in fields or "excluded" in fields:
            excluded = split_list(fields.get("excluded_services", fields.get("excluded")))
        else:
            excluded = list((existing or {}).get("excluded_services") or [])
        document = {
            "name": name,
            "description": _blank(scalar("description")),
            "destination": destination,
            "duration_days": duration_days,
            "selling_price_per_person": to_decimal128(price),
            "target_margin_percent": to_decimal128(margin),
            "currency": normalize_currency(scalar("currency") if "currency" in fields or existing is None else existing.get("currency")),
            "default_capacity": default_capacity,
            "services": services,
            "included_services": included,
            "excluded_services": excluded,
        }
        if "status" in fields and fields.get("status"):
            document["status"] = validate_package_status(fields["status"])
        elif existing:
            document["status"] = existing.get("status") or PackageStatus.ACTIVE.value
        else:
            document["status"] = PackageStatus.ACTIVE.value
        return document
