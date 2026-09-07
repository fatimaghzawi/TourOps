from __future__ import annotations

from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.expenses.services import present_expense
from apps.packages.services import present_service
from apps.packages.validators import (
    clean_destination,
    clean_service_lines,
    copy_service_lines,
    format_dates,
    join_list,
    normalize_currency,
    parse_optional_object_id,
    parse_non_negative_int,
    parse_positive_int,
    parse_price,
    parse_when,
    split_list,
)
from apps.tours.repositories import TourRepository
from apps.tours.schemas import available_seats
from apps.tours.validators import default_end, ensure_date_order, seat_status, validate_tour_status
from apps.notifications.constants import NotificationType
from apps.notifications.services import notify_for_type
from core.constants import Collections, DEFAULT_CURRENCY, PackageStatus, TourStatus
from core.costing import cost_sheet, serialize_costing
from core.exceptions import BusinessRuleViolation, DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.numbering import next_number
from core.utils import full_name, parse_object_id, serialize_id, utcnow


def _blank(value) -> str:
    return (str(value).strip() if value is not None else "") or ""


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def present_tour(
    document: dict,
    *,
    package: dict | None = None,
    costs=None,
    services=None,
    bookings=None,
    travelers=None,
    expenses=None,
) -> dict:
    destination = document.get("destination") or {}
    capacity = int(document.get("capacity") or 0)
    booked = int(document.get("booked_seats") or 0)
    held = int(document.get("held_seats") or 0)
    available = available_seats(capacity, booked, held)
    pct = min(int(round(booked / capacity * 100)), 100) if capacity else 0
    price = to_money(document.get("selling_price_per_person"))
    revenue = to_money(price * booked)
    cost_total = to_money(costs if costs is not None else ZERO)
    profit = to_money(revenue - cost_total)
    margin = round(float(profit / revenue * 100), 1) if revenue > ZERO else None
    start = document.get("start_date")
    end = document.get("end_date")
    included = document.get("included_services") or []
    excluded = document.get("excluded_services") or []
    package_name = (package or {}).get("name") if package else None
    costing = cost_sheet(
        services if services is not None else document.get("services"),
        capacity=capacity or 1,
        selling_price=price,
        margin_percent=(package or {}).get("target_margin_percent"),
        booked=booked,
    )
    return {
        "id": str(document["_id"]),
        "code": document.get("tour_code") or "",
        "tour_code": document.get("tour_code") or "",
        "name": document.get("name") or "",
        "description": document.get("description") or "",
        "city": destination.get("city") or "",
        "country": destination.get("country") or "",
        "destination": destination,
        "dates": format_dates(start, end),
        "start": start.strftime("%d %b %Y") if hasattr(start, "strftime") else "",
        "end": end.strftime("%d %b %Y") if hasattr(end, "strftime") else "",
        "start_date": start,
        "end_date": end,
        "capacity": capacity,
        "booked": booked,
        "booked_seats": booked,
        "held": held,
        "held_seats": held,
        "available": available,
        "pct": pct,
        "price": price,
        "selling_price_per_person": price,
        "currency": document.get("currency") or DEFAULT_CURRENCY,
        "costing": costing,
        "revenue": revenue,
        "costs": cost_total,
        "profit": profit,
        "margin": margin if margin is not None else 0,
        "cost_pct": min(int(round(float(cost_total / revenue * 100))), 100) if revenue > ZERO else (100 if cost_total > ZERO else 0),
        "status": document.get("status") or TourStatus.DRAFT.value,
        "package_id": serialize_id(document.get("package_id")),
        "package": package_name or "",
        "includes": join_list(included, sep=" + "),
        "included_services": included,
        "excluded": join_list(excluded),
        "excluded_services": excluded,
        "services": services or [],
        "bookings": bookings or [],
        "travelers": travelers or [],
        "expenses": expenses or [],
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "created_by": serialize_id(document.get("created_by")),
        "can_take_bookings": True,
        "booking_block_reason": "",
    }


def serialize_tour(presented: dict) -> dict:
    payload = dict(presented)
    for key in ("price", "selling_price_per_person", "revenue", "costs", "profit"):
        if isinstance(payload.get(key), Decimal):
            payload[key] = str(to_money(payload[key]))
    payload["costing"] = serialize_costing(payload.get("costing"))
    payload["start_date"] = _iso(payload.get("start_date"))
    payload["end_date"] = _iso(payload.get("end_date"))
    payload["created_at"] = _iso(payload.get("created_at"))
    payload["updated_at"] = _iso(payload.get("updated_at"))
    services = []
    for line in payload.get("services") or []:
        row = dict(line)
        for money_key in ("estimated_cost", "est"):
            if isinstance(row.get(money_key), Decimal):
                row[money_key] = str(to_money(row[money_key]))
        services.append(row)
    payload["services"] = services
    expenses = []
    for item in payload.get("expenses") or []:
        row = dict(item)
        for money_key in ("amount", "paid", "remaining"):
            if isinstance(row.get(money_key), Decimal):
                row[money_key] = str(to_money(row[money_key]))
        expenses.append(row)
    payload["expenses"] = expenses
    bookings = []
    for item in payload.get("bookings") or []:
        row = dict(item)
        if isinstance(row.get("total"), Decimal):
            row["total"] = str(to_money(row["total"]))
        bookings.append(row)
    payload["bookings"] = bookings
    return payload


class TourService:
    def __init__(self, repository: TourRepository | None = None):
        self.repository = repository or TourRepository()

    def list_items(self, *, status: str | None = None, package_id=None) -> list[dict]:
        extra = {}
        if status:
            extra["status"] = validate_tour_status(status)
        if package_id:
            extra["package_id"] = parse_object_id(package_id, field="package_id")
        return self.repository.list_tours(extra or None)

    def list_presented(self, **filters) -> list[dict]:
        costs = self.repository.costs_by_tour()
        rows = []
        for document in self.list_items(**filters):
            package = self._package(document.get("package_id"))
            services = [self._service(line) for line in document.get("services") or []]
            presented = present_tour(
                document,
                package=package,
                costs=costs.get(str(document["_id"]), ZERO),
                services=services,
            )
            presented["services"] = []
            rows.append(self._with_booking_gate(document, presented))
        return rows

    def get(self, tour_id) -> dict:
        try:
            document = self.repository.find_by_id(tour_id)
        except ValidationError as extra:
            raise NotFoundError("Tour not found.") from extra
        if not document:
            raise NotFoundError("Tour not found.")
        return document

    def get_presented(self, tour_id, *, include_extras: bool = True) -> dict:
        document = self.get(tour_id)
        package = self._package(document.get("package_id"))
        services = bookings = travelers = expenses = None
        costs = None
        if include_extras:
            services = [self._service(line) for line in document.get("services") or []]
            bookings, travelers = self._bookings(document["_id"])
            expenses = [present_expense(row) for row in self.repository.list_expenses_for(document["_id"])]
            costs = sum((to_money(row.get("amount")) for row in expenses), ZERO)
        else:
            costs = self.repository.costs_by_tour().get(str(document["_id"]), ZERO)
        presented = present_tour(
            document,
            package=package,
            costs=costs,
            services=services,
            bookings=bookings,
            travelers=travelers,
            expenses=expenses,
        )
        presented["activity"] = self._activity(document, bookings or [], expenses or [])
        if include_extras:
            from apps.supplier_reservations.services import SupplierReservationService

            presented["reservations"] = SupplierReservationService().list_for_tour(document["_id"])
            presented["accommodation"] = SupplierReservationService().accommodation_snapshot(document["_id"])
        else:
            presented["reservations"] = []
            presented["accommodation"] = {}
        return self._with_booking_gate(document, presented)

    def assert_ready_for_customer_bookings(self, tour_id) -> None:
        document = self.get(tour_id)
        reason = self.customer_booking_block_reason(document)
        if reason:
            raise BusinessRuleViolation(reason)

    def customer_booking_block_reason(self, tour: dict) -> str | None:
        from apps.supplier_reservations.services import SupplierReservationService

        return SupplierReservationService().customer_booking_block_reason(tour)

    def _with_booking_gate(self, document: dict, presented: dict) -> dict:
        reason = self.customer_booking_block_reason(document)
        presented["booking_block_reason"] = reason or ""
        presented["can_take_bookings"] = reason is None
        return presented

    def availability(self) -> list[dict]:
        rows = []
        for row in self.list_presented():
            if row["status"] == TourStatus.CANCELLED.value:
                continue
            rows.append(row)
        return rows

    def create(self, *, actor_id, **fields) -> dict:
        package = self._load_package(fields.get("package_id"), required=True)
        if package.get("status") == PackageStatus.INACTIVE.value:
            raise BusinessRuleViolation("This package is inactive. Activate it before creating a departure.")
        document = self._document(existing=None, package=package, **fields)
        now = utcnow()
        document.update(
            {
                "tour_code": next_number(Collections.TOURS),
                "created_by": parse_object_id(actor_id, field="created_by"),
                "created_at": now,
                "updated_at": now,
            }
        )
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A tour with this code already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the tour.") from extra
        document["_id"] = result.inserted_id
        notify_for_type(
            NotificationType.TOUR.value,
            title=f"Tour {document.get('tour_code')}",
            message=f"{document.get('name') or 'A departure'} is on the board for agents to sell.",
            related_entity_type="tours",
            related_entity_id=document["_id"],
            exclude_user_id=actor_id,
        )
        return self.get(document["_id"])

    def update(self, tour_id, *, actor_id=None, **fields) -> dict:
        existing = self.get(tour_id)
        requested_status = fields.get("status")
        if requested_status == TourStatus.CANCELLED.value and existing.get("status") != TourStatus.CANCELLED.value:
            booked = int(existing.get("booked_seats") or 0)
            if booked > 0 or self.repository.has_live_bookings(existing["_id"]):
                raise BusinessRuleViolation("Cancel live bookings before cancelling this tour.")
        package = self._load_package(existing.get("package_id"), required=True)
        if "package_id" in fields and fields.get("package_id"):
            incoming = serialize_id(fields.get("package_id"))
            current = serialize_id(existing.get("package_id"))
            if incoming and current and incoming != current:
                raise BusinessRuleViolation("A tour cannot be moved to a different package.")
        updates = self._document(existing=existing, package=package, **fields)
        if actor_id:
            updates["updated_by"] = parse_object_id(actor_id, field="updated_by")
        updates["updated_at"] = utcnow()
        try:
            self.repository.update(existing["_id"], updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not update the tour.") from extra
        return self.get(existing["_id"])

    def adjust_booked_seats(self, tour_id, delta: int) -> dict:
        document = self.get(tour_id)
        booked = int(document.get("booked_seats") or 0) + int(delta)
        if booked < 0:
            booked = 0
        return self.update(tour_id, booked_seats=booked)

    def try_reserve_seats(self, tour_id, seats: int) -> dict:
        count = int(seats)
        if count <= 0:
            raise ValidationError("Seat count must be positive.")
        document = self.get(tour_id)
        status = document.get("status")
        if status in {TourStatus.CANCELLED.value, TourStatus.COMPLETED.value, TourStatus.DRAFT.value}:
            raise BusinessRuleViolation("This tour is not open for new confirmed bookings.")
        capacity = int(document.get("capacity") or 0)
        max_booked = capacity - count
        updated = self.repository.try_increment_booked_seats(document["_id"], count, max_booked=max_booked)
        if not updated:
            booked = int(document.get("booked_seats") or 0)
            raise BusinessRuleViolation(
                f"Not enough tour seats. {booked} of {capacity} are already booked; this booking needs {count}."
            )
        return self._sync_seat_status(updated)

    def release_reserved_seats(self, tour_id, seats: int) -> dict:
        count = int(seats)
        if count <= 0:
            return self.get(tour_id)
        updated = self.repository.try_decrement_booked_seats(tour_id, count)
        if not updated:
            return self.get(tour_id)
        return self._sync_seat_status(updated)

    def _sync_seat_status(self, document: dict) -> dict:
        booked = int(document.get("booked_seats") or 0)
        capacity = int(document.get("capacity") or 0)
        status = seat_status(document.get("status"), capacity=capacity, booked=booked)
        self.repository.update(
            document["_id"],
            {"booked_seats": booked, "status": status, "updated_at": utcnow()},
        )
        return self.get(document["_id"])

    def soft_delete(self, tour_id, *, actor_id) -> None:
        document = self.get(tour_id)
        booked = int(document.get("booked_seats") or 0)
        if booked > 0 or self.repository.has_live_bookings(document["_id"]):
            raise ValidationError("Cannot delete a tour that already has bookings.")
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not delete the tour.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Tour not found.")

    def _load_package(self, package_id, *, required: bool = False):
        oid = parse_optional_object_id(package_id, field="package_id")
        if not oid:
            if required:
                raise ValidationError("Select a package. A tour is a dated departure of a package.")
            return None
        package = self.repository.find_package(oid)
        if not package:
            raise ValidationError("Package not found.")
        return package

    def _package(self, package_id):
        if not package_id:
            return None
        try:
            return self.repository.find_package(package_id)
        except ValidationError:
            return None

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

    def _bookings(self, tour_id) -> tuple[list[dict], list[dict]]:
        bookings = []
        travelers = []
        for document in self.repository.list_bookings_for(tour_id):
            customer = None
            if document.get("customer_id"):
                try:
                    customer = self.repository.find_customer(document["customer_id"])
                except ValidationError:
                    customer = None
            pricing = document.get("pricing") or {}
            total = to_money(pricing.get("total_amount") if isinstance(pricing, dict) else ZERO)
            customer_name = "—"
            if customer:
                customer_name = customer.get("name") or full_name(customer.get("first_name"), customer.get("last_name")) or "—"
            bookings.append(
                {
                    "id": str(document["_id"]),
                    "number": document.get("booking_number") or "",
                    "customer": customer_name,
                    "travelers": document.get("travelers_count") or len(document.get("travelers") or []),
                    "status": document.get("booking_status") or "",
                    "total": total,
                }
            )
            if document.get("booking_status") != "CANCELLED":
                for person in document.get("travelers") or []:
                    if not isinstance(person, dict):
                        continue
                    travelers.append(
                        {
                            "name": full_name(person.get("first_name"), person.get("last_name")) or person.get("name") or "Traveler",
                            "passport": person.get("passport_number") or "—",
                            "type": person.get("type") or "—",
                        }
                    )
        return bookings, travelers

    def _activity(self, document: dict, bookings: list, expenses: list) -> list[dict]:
        items = []
        created = document.get("created_at")
        if created:
            items.append({"text": f"Departure created · {created.strftime('%d %b %Y') if hasattr(created, 'strftime') else created}"})
        for booking in bookings[:5]:
            items.append({"text": f"Booking {booking.get('number') or ''} · {booking.get('customer') or ''}".strip(" ·")})
        for expense in expenses[:5]:
            items.append({"text": f"Expense {expense.get('number') or ''} recorded"})
        updated = document.get("updated_at")
        if updated and updated != created:
            items.append({"text": f"Last updated · {updated.strftime('%d %b %Y') if hasattr(updated, 'strftime') else updated}"})
        return items

    def _document(self, *, existing, package, **fields) -> dict:
        previous = existing or {}
        source = package or {}

        def scalar(key, alias=None, nested=None, fallback=None):
            if key in fields:
                return fields[key]
            if alias and alias in fields:
                return fields[alias]
            if nested and isinstance(fields.get(nested), dict) and key in fields[nested]:
                return fields[nested][key]
            if key in previous:
                return previous.get(key)
            if nested and previous.get(nested):
                return (previous.get(nested) or {}).get(key)
            if fallback == "package":
                if nested:
                    return (source.get(nested) or {}).get(key)
                if key == "capacity":
                    return source.get("default_capacity")
                if key == "selling_price_per_person":
                    return source.get("selling_price_per_person")
                return source.get(key)
            return None

        name = _blank(scalar("name"))
        if not name:
            name = _blank((package or {}).get("name"))
        if not name:
            raise ValidationError("Tour name is required.")
        city = scalar("city", nested="destination")
        country = scalar("country", nested="destination")
        if city in (None, "") and package:
            city = (package.get("destination") or {}).get("city")
            country = country or (package.get("destination") or {}).get("country")
        elif city in (None, "") and existing:
            city = (previous.get("destination") or {}).get("city")
            country = country or (previous.get("destination") or {}).get("country")
        destination = clean_destination(city=city, country=country)
        start = parse_when(scalar("start_date"), field="start_date") if ("start_date" in fields or not existing) else previous.get("start_date")
        if start is None and existing:
            start = previous.get("start_date")
        if start is None:
            raise ValidationError("Start date is required.")
        end_raw = scalar("end_date")
        if end_raw in (None, "") and not existing:
            end = default_end(start, source.get("duration_days"))
        elif "end_date" in fields or not existing:
            end = parse_when(end_raw, field="end_date") if end_raw not in (None, "") else default_end(start, source.get("duration_days"))
        else:
            end = previous.get("end_date")
        if end is None:
            raise ValidationError("End date is required.")
        ensure_date_order(start, end)

        capacity_raw = scalar("capacity", fallback="package")
        if capacity_raw is None:
            raise ValidationError("Capacity is required.")
        capacity = parse_positive_int(capacity_raw, field="capacity")
        booked = parse_non_negative_int(
            fields["booked_seats"] if "booked_seats" in fields else previous.get("booked_seats", 0),
            field="booked_seats",
            default=0,
        )
        if capacity < booked:
            raise ValidationError("Capacity cannot be lower than booked seats.")

        price_raw = scalar("selling_price_per_person", alias="price", fallback="package")
        if price_raw is None:
            raise ValidationError("Price is required.")
        price = parse_price(price_raw)

        if "service_ids" in fields:
            services = clean_service_lines(
                [{"supplier_service_id": item} for item in (fields.get("service_ids") or [])],
                lookup_supplier=self._lookup_supplier,
                lookup_offering=self._lookup_offering,
                require_active=True,
            )
        elif "services" in fields:
            services = clean_service_lines(
                fields.get("services"),
                lookup_supplier=self._lookup_supplier,
                lookup_offering=self._lookup_offering,
                require_active=not existing,
                existing_lines=previous.get("services"),
            )
        elif existing:
            services = list(previous.get("services") or [])
        else:
            services = copy_service_lines(source.get("services"))

        if "included_services" in fields or "includes" in fields:
            included = split_list(fields.get("included_services", fields.get("includes")))
        elif existing:
            included = list(previous.get("included_services") or [])
        else:
            included = list(source.get("included_services") or [])

        if "excluded_services" in fields or "excluded" in fields:
            excluded = split_list(fields.get("excluded_services", fields.get("excluded")))
        elif existing:
            excluded = list(previous.get("excluded_services") or [])
        else:
            excluded = list(source.get("excluded_services") or [])

        description = scalar("description", fallback="package")
        if description is None:
            description = ""
        currency_raw = scalar("currency")
        if currency_raw is None:
            currency_raw = previous.get("currency") or source.get("currency") or DEFAULT_CURRENCY

        requested_status = fields.get("status") if "status" in fields else previous.get("status") or TourStatus.AVAILABLE.value
        status = seat_status(requested_status or TourStatus.AVAILABLE.value, capacity=capacity, booked=booked)
        package_id = parse_optional_object_id(fields.get("package_id", previous.get("package_id") if existing else (source.get("_id") if source else None)), field="package_id")

        return {
            "name": name,
            "package_id": package_id,
            "destination": destination,
            "description": _blank(description),
            "start_date": start,
            "end_date": end,
            "capacity": capacity,
            "booked_seats": booked,
            "selling_price_per_person": to_decimal128(price),
            "currency": normalize_currency(currency_raw),
            "status": status,
            "services": services,
            "included_services": included,
            "excluded_services": excluded,
        }
