from __future__ import annotations

from datetime import date, datetime

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.notifications.constants import NotificationType
from apps.notifications.services import notify_for_type
from apps.packages.validators import format_dates, parse_when
from apps.supplier_reservations.constants import (
    SERVICE_TYPE_LABELS,
    STATUS_LABELS,
)
from apps.supplier_reservations.repositories import SupplierReservationRepository
from apps.supplier_reservations.validators import (
    validate_service_type,
    validate_status,
)
from core.constants import (
    BookingStatus,
    Collections,
    SupplierReservationStatus,
    SupplierType,
)
from core.exceptions import BusinessRuleViolation, DatabaseUnavailableError, NotFoundError, ValidationError
from core.numbering import next_number
from core.utils import full_name, parse_object_id, serialize_id, utcnow


def _blank(value) -> str | None:
    text = (str(value).strip() if value is not None else "") or None
    return text


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def present_reservation(document: dict, *, supplier: dict | None = None, tour: dict | None = None) -> dict:
    status = document.get("status") or SupplierReservationStatus.REQUESTED.value
    service_type = document.get("service_type") or ""
    start = document.get("start_date")
    end = document.get("end_date")
    release = document.get("release_date")
    today = utcnow().date()
    release_day = _as_date(release)
    start_day = _as_date(start)
    release_days = (release_day - today).days if release_day else None
    created = document.get("created_at")
    return {
        "id": str(document["_id"]),
        "number": document.get("reservation_number") or "",
        "reservation_number": document.get("reservation_number") or "",
        "tour_id": serialize_id(document.get("tour_id")),
        "tour": (tour or {}).get("name") or (tour or {}).get("tour_code") or "",
        "tour_code": (tour or {}).get("tour_code") or "",
        "supplier_id": serialize_id(document.get("supplier_id")),
        "supplier": (supplier or {}).get("name") or "—",
        "supplier_email": (supplier or {}).get("email") or "",
        "supplier_phone": (supplier or {}).get("phone") or "",
        "service_type": service_type,
        "service_label": SERVICE_TYPE_LABELS.get(service_type, service_type),
        "is_hotel": service_type == SupplierType.HOTEL.value,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "confirmation_number": document.get("confirmation_number") or "",
        "dates": format_dates(start, end),
        "start_date": start,
        "end_date": end,
        "start_label": start.strftime("%d %b %Y") if hasattr(start, "strftime") else (str(start) if start else ""),
        "end_label": end.strftime("%d %b %Y") if hasattr(end, "strftime") else (str(end) if end else ""),
        "release_date": release,
        "release": release.strftime("%d %b %Y") if hasattr(release, "strftime") else (str(release) if release else ""),
        "release_days": release_days,
        "release_approaching": release_days is not None and 0 <= release_days <= 7,
        "release_passed": release_days is not None and release_days < 0,
        "quantity": document.get("quantity"),
        "notes": document.get("notes") or "",
        "is_cancelled": status == SupplierReservationStatus.CANCELLED.value,
        "is_confirmed": status == SupplierReservationStatus.CONFIRMED.value,
        "is_requested": status == SupplierReservationStatus.REQUESTED.value,
        "is_upcoming": bool(start_day and start_day >= today and status != SupplierReservationStatus.CANCELLED.value),
        "created_at": created,
        "created_label": created.strftime("%d %b %Y, %H:%M") if hasattr(created, "strftime") else (str(created) if created else ""),
        "updated_at": document.get("updated_at"),
    }


class SupplierReservationService:
    def __init__(self, repository: SupplierReservationRepository | None = None):
        self.repository = repository or SupplierReservationRepository()

    def customer_booking_block_reason(self, tour: dict) -> str | None:
        rows = self.repository.list_for_tour(tour["_id"])
        confirmed = set()
        waiting = []
        for row in rows:
            status = row.get("status")
            if status == SupplierReservationStatus.CANCELLED.value:
                continue
            supplier_id = str(row.get("supplier_id") or "")
            if status == SupplierReservationStatus.CONFIRMED.value:
                if supplier_id:
                    confirmed.add(supplier_id)
                continue
            waiting.append(row)
        if waiting:
            return "This tour cannot take client bookings until every planned supplier has confirmed."
        for line in tour.get("services") or []:
            supplier_id = str(line.get("supplier_id") or "")
            if supplier_id and supplier_id not in confirmed:
                return "This tour cannot take client bookings until every planned supplier has confirmed."
        return None

    def list_items(self, *, tour_id=None, supplier_id=None, status: str | None = None) -> list[dict]:
        extra = {}
        if tour_id:
            extra["tour_id"] = parse_object_id(tour_id, field="tour_id")
        if supplier_id:
            extra["supplier_id"] = parse_object_id(supplier_id, field="supplier_id")
        if status:
            extra["status"] = validate_status(status)
        return self.repository.list_reservations(extra or None)

    def list_presented(self, **filters) -> list[dict]:
        return [self._present(doc) for doc in self.list_items(**filters)]

    def list_for_tour(self, tour_id) -> list[dict]:
        tour = self._require_tour(tour_id)
        return [self._present(doc, tour=tour) for doc in self.repository.list_for_tour(tour["_id"])]

    def get(self, reservation_id) -> dict:
        try:
            document = self.repository.find_by_id(reservation_id)
        except ValidationError as extra:
            raise NotFoundError("Supplier reservation not found.") from extra
        if not document:
            raise NotFoundError("Supplier reservation not found.")
        return document

    def get_presented(self, reservation_id) -> dict:
        return self._present(self.get(reservation_id))

    def create(
        self,
        *,
        actor_id,
        tour_id,
        supplier_id,
        start_date=None,
        end_date=None,
        status: str | None = None,
        confirmation_number: str | None = None,
        release_date=None,
        quantity=None,
        notes: str | None = None,
        service_type: str | None = None,
    ) -> dict:
        tour = self._require_tour(tour_id)
        supplier = self._require_supplier(supplier_id)
        service_type = validate_service_type(service_type or supplier.get("supplier_type") or "")
        start = parse_when(start_date, field="start_date") if start_date not in (None, "") else tour.get("start_date")
        end = parse_when(end_date, field="end_date") if end_date not in (None, "") else tour.get("end_date")
        if start is None or end is None:
            raise ValidationError("Start and end dates are required.")
        if end < start:
            raise ValidationError("End date cannot be before start date.")
        release = parse_when(release_date, field="release_date", required=False) if release_date not in (None, "") else None

        qty = None
        if quantity not in (None, ""):
            qty = int(quantity)
            if qty < 1:
                raise ValidationError("Quantity must be at least 1.")

        next_status = validate_status(status or SupplierReservationStatus.REQUESTED.value)
        confirmation = _blank(confirmation_number)
        if next_status == SupplierReservationStatus.CONFIRMED.value and not confirmation:
            raise ValidationError("A confirmation number is required once the supplier confirms.")
        if next_status == SupplierReservationStatus.CANCELLED.value:
            raise ValidationError("Create the reservation first, then cancel it.")

        now = utcnow()
        document = {
            "reservation_number": next_number(Collections.SUPPLIER_RESERVATIONS),
            "tour_id": tour["_id"],
            "supplier_id": supplier["_id"],
            "service_type": service_type,
            "start_date": start,
            "end_date": end,
            "status": next_status,
            "confirmation_number": confirmation,
            "release_date": release,
            "quantity": qty,
            "notes": _blank(notes),
            "recorded_by": parse_object_id(actor_id, field="recorded_by"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A supplier reservation with this number already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the supplier reservation.") from extra
        document["_id"] = result.inserted_id
        saved = self.get(document["_id"])
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.CREATED.value,
            entity_type="supplier_reservations",
            entity_id=saved["_id"],
            description=f"Recorded supplier reservation {saved.get('reservation_number')}.",
        )
        notify_for_type(
            NotificationType.TOUR.value,
            title=f"Reservation {saved.get('reservation_number')}",
            message="A supplier arrangement was recorded for a departure.",
            related_entity_type="supplier_reservations",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def update(self, reservation_id, *, actor_id=None, **fields) -> dict:
        document = self.get(reservation_id)
        fields.pop("room_allocations", None)
        if document.get("status") == SupplierReservationStatus.CANCELLED.value:
            raise BusinessRuleViolation("A cancelled reservation cannot be edited.")
        updates = {}
        if "start_date" in fields and fields["start_date"] not in (None, ""):
            updates["start_date"] = parse_when(fields["start_date"], field="start_date")
        if "end_date" in fields and fields["end_date"] not in (None, ""):
            updates["end_date"] = parse_when(fields["end_date"], field="end_date")
        start = updates.get("start_date", document.get("start_date"))
        end = updates.get("end_date", document.get("end_date"))
        if start and end and end < start:
            raise ValidationError("End date cannot be before start date.")
        if "release_date" in fields:
            updates["release_date"] = (
                parse_when(fields["release_date"], field="release_date", required=False)
                if fields["release_date"] not in (None, "")
                else None
            )
        if "notes" in fields:
            updates["notes"] = _blank(fields["notes"])
        if "confirmation_number" in fields:
            updates["confirmation_number"] = _blank(fields["confirmation_number"])
        if "quantity" in fields:
            if fields["quantity"] in (None, ""):
                updates["quantity"] = None
            else:
                qty = int(fields["quantity"])
                if qty < 1:
                    raise ValidationError("Quantity must be at least 1.")
                updates["quantity"] = qty
        if "status" in fields and fields["status"] is not None:
            updates["status"] = self._next_status(document, fields["status"], updates)
        if not updates:
            return document
        updates["updated_at"] = utcnow()
        try:
            self.repository.update(document["_id"], updates)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not update the supplier reservation.") from extra
        saved = self.get(document["_id"])
        safe_audit(
            actor_id=actor_id or document.get("recorded_by"),
            action=AuditAction.UPDATED.value,
            entity_type="supplier_reservations",
            entity_id=saved["_id"],
            description=f"Updated supplier reservation {saved.get('reservation_number')}.",
        )
        return saved

    def confirm(self, reservation_id, *, actor_id, confirmation_number: str, notes: str | None = None) -> dict:
        extra = {}
        if notes not in (None, ""):
            document = self.get(reservation_id)
            existing = (document.get("notes") or "").strip()
            extra["notes"] = f"{existing}\n{notes.strip()}".strip() if existing else notes.strip()
        saved = self.update(
            reservation_id,
            actor_id=actor_id,
            status=SupplierReservationStatus.CONFIRMED.value,
            confirmation_number=confirmation_number,
            **extra,
        )
        notify_for_type(
            NotificationType.TOUR.value,
            title=f"Reservation {saved.get('reservation_number')}",
            message="The supplier confirmed. Update the client itinerary if needed.",
            related_entity_type="supplier_reservations",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def cancel(self, reservation_id, *, actor_id) -> dict:
        saved = self.update(reservation_id, actor_id=actor_id, status=SupplierReservationStatus.CANCELLED.value)
        notify_for_type(
            NotificationType.TOUR.value,
            title=f"Reservation {saved.get('reservation_number')}",
            message="A supplier reservation was cancelled.",
            related_entity_type="supplier_reservations",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def accommodation_snapshot(self, tour_id) -> dict:
        tour = self._require_tour(tour_id)
        reservations = [self._present(doc, tour=tour) for doc in self.repository.list_for_tour(tour["_id"])]
        hotels = [
            row
            for row in reservations
            if row["is_hotel"] and row["status"] != SupplierReservationStatus.CANCELLED.value
        ]
        travelers = self._confirmed_travelers(tour["_id"])
        confirmed_count = len(travelers)
        today = utcnow().date()
        warnings = []
        for hotel in hotels:
            release = _as_date(hotel.get("release_date"))
            if release and release <= today:
                warnings.append(f"{hotel['supplier']} release date {hotel['release']} has passed.")
            elif release and 0 <= (release - today).days <= 7:
                warnings.append(f"{hotel['supplier']} release date {hotel['release']} is approaching.")
        return {
            "tour_id": str(tour["_id"]),
            "tour_name": tour.get("name") or tour.get("tour_code") or "Tour",
            "tour_code": tour.get("tour_code") or "",
            "dates": format_dates(tour.get("start_date"), tour.get("end_date")),
            "confirmed_travelers": confirmed_count,
            "hotels": hotels,
            "reservations": reservations,
            "warnings": warnings,
        }

    def list_supplier_options(self) -> list[tuple[str, str]]:
        return [
            (str(doc["_id"]), doc.get("name") or doc.get("supplier_number") or "Supplier")
            for doc in self.repository.list_suppliers()
        ]

    def match_planned(self, services: list[dict], reservations: list[dict]) -> list[dict]:
        by_supplier: dict[str, list[dict]] = {}
        for row in reservations or []:
            if row.get("is_cancelled"):
                continue
            by_supplier.setdefault(row.get("supplier_id") or "", []).append(row)
        matched = []
        for line in services or []:
            linked = by_supplier.get(line.get("supplier_id") or "") or []
            matched.append(
                {
                    "title": line.get("title") or line.get("description") or "Service",
                    "supplier": line.get("supplier") or "—",
                    "supplier_id": line.get("supplier_id"),
                    "type_label": line.get("type_label") or line.get("supplier_type") or "",
                    "estimated_cost": line.get("estimated_cost") or line.get("est"),
                    "basis_label": line.get("basis_label") or "",
                    "reservations": linked,
                    "has_reservation": bool(linked),
                }
            )
        return matched

    def ops_desk(self) -> dict:
        rows = self.list_presented()
        live = [row for row in rows if not row["is_cancelled"]]
        requested = [row for row in live if row["is_requested"]]
        confirmed = [row for row in live if row["is_confirmed"]]
        upcoming = [row for row in live if row.get("is_upcoming")]
        release_watch = [row for row in live if row.get("release_approaching") or row.get("release_passed")]
        return {
            "requested": len(requested),
            "confirmed": len(confirmed),
            "upcoming": len(upcoming),
            "release_watch": release_watch,
            "awaiting": requested,
            "reservations": rows,
        }

    def related_expenses(self, *, supplier_id, tour_id) -> list[dict]:
        from apps.expenses.services import ExpenseService

        rows = []
        for expense in ExpenseService().list_presented(supplier_id=supplier_id):
            if tour_id and expense.get("tour_id") and expense.get("tour_id") != str(tour_id):
                continue
            rows.append(expense)
        return rows

    def _next_status(self, document: dict, requested, updates: dict) -> str:
        status = validate_status(requested)
        current = document.get("status")
        if current == status:
            return status
        if current == SupplierReservationStatus.CANCELLED.value:
            raise BusinessRuleViolation("A cancelled reservation cannot change status.")
        if status == SupplierReservationStatus.CONFIRMED.value:
            confirmation = updates.get("confirmation_number", document.get("confirmation_number"))
            if not confirmation:
                raise ValidationError("A confirmation number is required once the supplier confirms.")
        if status == SupplierReservationStatus.REQUESTED.value and current == SupplierReservationStatus.CONFIRMED.value:
            return status
        return status

    def _require_tour(self, tour_id) -> dict:
        try:
            tour = self.repository.find_tour(tour_id)
        except ValidationError as extra:
            raise NotFoundError("Tour not found.") from extra
        if not tour:
            raise NotFoundError("Tour not found.")
        return tour

    def _require_supplier(self, supplier_id) -> dict:
        try:
            supplier = self.repository.find_supplier(supplier_id)
        except ValidationError as extra:
            raise ValidationError("Supplier not found.") from extra
        if not supplier:
            raise ValidationError("Supplier not found.")
        return supplier

    def _present(self, document: dict, *, tour=None, supplier=None) -> dict:
        if supplier is None and document.get("supplier_id"):
            supplier = self.repository.find_supplier(document["supplier_id"])
        if tour is None and document.get("tour_id"):
            tour = self.repository.find_tour(document["tour_id"])
        return present_reservation(document, supplier=supplier, tour=tour)

    def _confirmed_travelers(self, tour_id) -> list[dict]:
        from apps.bookings.services import present_traveler

        travelers = []
        query = {"tour_id": tour_id, "booking_status": BookingStatus.CONFIRMED.value, "is_deleted": {"$ne": True}}
        for booking in self.repository.bookings.find(query):
            for index, person in enumerate(booking.get("travelers") or []):
                if not isinstance(person, dict):
                    continue
                travelers.append(present_traveler(person, index=index, booking=booking))
        return travelers
