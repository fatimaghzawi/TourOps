from __future__ import annotations

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.bookings.constants import STATUS_LABELS
from apps.bookings.repositories import BookingRepository
from apps.notifications.constants import NotificationType
from apps.notifications.services import notify_for_type
from apps.packages.validators import format_dates, parse_optional_object_id, parse_when
from apps.tours.services import TourService
from core.constants import BookingStatus, Collections, DEFAULT_CURRENCY, DiscountType, PaymentStatus, TourStatus
from core.exceptions import BusinessRuleViolation, DatabaseUnavailableError, NotFoundError, TourOpsError, ValidationError
from core.money import ZERO, to_decimal, to_decimal128, to_money
from core.numbering import next_number
from core.utils import full_name, parse_object_id, serialize_id, utcnow


def present_traveler(person: dict, *, index: int = 0, booking: dict | None = None) -> dict:
    name = full_name(person.get("first_name"), person.get("last_name")) or person.get("name") or "Traveler"
    dob = person.get("date_of_birth")
    return {
        "index": index,
        "booking_id": serialize_id((booking or {}).get("_id")),
        "booking_number": (booking or {}).get("booking_number") or "",
        "first_name": person.get("first_name") or "",
        "last_name": person.get("last_name") or "",
        "name": name,
        "passport": person.get("passport_number") or "",
        "passport_number": person.get("passport_number") or "",
        "nationality": person.get("nationality") or "",
        "date_of_birth": dob,
        "dob": dob.strftime("%d %b %Y") if hasattr(dob, "strftime") else (str(dob) if dob else ""),
        "room_type": person.get("room_type") or "",
        "room_number": person.get("room_number") or "",
        "hotel_reservation_id": serialize_id(person.get("hotel_reservation_id")),
        "type": person.get("type") or "",
    }


def _pricing_from(tour: dict, traveler_count: int) -> dict:
    unit = to_money(tour.get("selling_price_per_person"))
    subtotal = to_money(unit * traveler_count)
    return {
        "unit_price": to_decimal128(unit),
        "subtotal": to_decimal128(subtotal),
        "discount_type": DiscountType.NONE.value,
        "discount_value": to_decimal128(ZERO),
        "discount_amount": to_decimal128(ZERO),
        "taxable_amount": to_decimal128(subtotal),
        "tax_rate": to_decimal128(ZERO),
        "tax_amount": to_decimal128(ZERO),
        "total_amount": to_decimal128(subtotal),
    }


def present_booking(document: dict, *, customer: dict | None = None, tour: dict | None = None) -> dict:
    pricing = document.get("pricing") or {}
    travelers = document.get("travelers") or []
    count = int(document.get("travelers_count") or len(travelers) or 0)
    customer_name = "—"
    if customer:
        customer_name = full_name(customer.get("first_name"), customer.get("last_name")) or customer.get("email") or "—"
    tour_name = (tour or {}).get("name") or (tour or {}).get("tour_code") or ""
    start = (tour or {}).get("start_date")
    end = (tour or {}).get("end_date")
    status = document.get("booking_status") or BookingStatus.PENDING.value
    return {
        "id": str(document["_id"]),
        "number": document.get("booking_number") or "",
        "booking_number": document.get("booking_number") or "",
        "customer_id": serialize_id(document.get("customer_id")),
        "customer": customer_name,
        "tour_id": serialize_id(document.get("tour_id")),
        "tour": tour_name,
        "product": tour_name,
        "dates": format_dates(start, end),
        "travelers_count": count,
        "travelers": [
            present_traveler(person, index=index, booking=document)
            for index, person in enumerate(travelers)
            if isinstance(person, dict)
        ],
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "payment_status": document.get("payment_status") or PaymentStatus.UNPAID.value,
        "pay": document.get("payment_status") or PaymentStatus.UNPAID.value,
        "total": to_money(pricing.get("total_amount")),
        "currency": document.get("currency") or (tour or {}).get("currency") or DEFAULT_CURRENCY,
        "notes": document.get("notes") or "",
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def clean_travelers(raw) -> list[dict]:
    if raw in (None, ""):
        raise ValidationError("At least one traveler is required.")
    if not isinstance(raw, list):
        raise ValidationError("Travelers must be a list.")
    people = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"Traveler {index} is invalid.")
        first = (item.get("first_name") or "").strip()
        last = (item.get("last_name") or "").strip()
        if not first or not last:
            raise ValidationError(f"Traveler {index} needs a first and last name.")
        dob = item.get("date_of_birth")
        parsed_dob = parse_when(dob, field="date_of_birth", required=False) if dob not in (None, "") else None
        hotel_id = parse_optional_object_id(item.get("hotel_reservation_id"), field="hotel_reservation_id")
        people.append(
            {
                "first_name": first,
                "last_name": last,
                "passport_number": (item.get("passport_number") or item.get("passport") or "").strip() or None,
                "nationality": (item.get("nationality") or "").strip() or None,
                "date_of_birth": parsed_dob,
                "room_type": (item.get("room_type") or "").strip().upper() or None,
                "room_number": (item.get("room_number") or "").strip() or None,
                "hotel_reservation_id": hotel_id,
            }
        )
    if not people:
        raise ValidationError("At least one traveler is required.")
    return people


class BookingService:
    def __init__(
        self,
        repository: BookingRepository | None = None,
        tours: TourService | None = None,
    ):
        self.repository = repository or BookingRepository()
        self.tours = tours or TourService()

    def list_items(self, *, tour_id=None, customer_id=None, status: str | None = None) -> list[dict]:
        extra = {}
        if tour_id:
            extra["tour_id"] = parse_object_id(tour_id, field="tour_id")
        if customer_id:
            extra["customer_id"] = parse_object_id(customer_id, field="customer_id")
        if status:
            extra["booking_status"] = (status or "").strip().upper()
        return self.repository.list_bookings(extra or None)

    def list_presented(self, **filters) -> list[dict]:
        return [self._present(doc) for doc in self.list_items(**filters)]

    def get(self, booking_id) -> dict:
        try:
            document = self.repository.find_by_id(booking_id)
        except ValidationError as extra:
            raise NotFoundError("Booking not found.") from extra
        if not document:
            raise NotFoundError("Booking not found.")
        return document

    def get_presented(self, booking_id) -> dict:
        return self._present(self.get(booking_id))

    def create(self, *, actor_id, customer_id, tour_id, travelers, notes: str | None = None) -> dict:
        customer = self.repository.find_customer(customer_id)
        if not customer:
            raise ValidationError("Customer not found.")
        tour = self.tours.get(tour_id)
        if tour.get("status") in {TourStatus.CANCELLED.value, TourStatus.COMPLETED.value, TourStatus.DRAFT.value}:
            raise BusinessRuleViolation("This tour is not open for new bookings.")
        self.tours.assert_ready_for_customer_bookings(tour["_id"])
        people = clean_travelers(travelers)
        now = utcnow()
        document = {
            "booking_number": next_number(Collections.BOOKINGS),
            "customer_id": customer["_id"],
            "tour_id": tour["_id"],
            "travelers_count": len(people),
            "travelers": people,
            "booking_date": now,
            "pricing": _pricing_from(tour, len(people)),
            "currency": tour.get("currency") or DEFAULT_CURRENCY,
            "booking_status": BookingStatus.PENDING.value,
            "payment_status": PaymentStatus.UNPAID.value,
            "notes": (notes or "").strip() or None,
            "created_by": parse_object_id(actor_id, field="created_by"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            raise ValidationError("A booking with this number already exists.") from extra
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save the booking.") from extra
        document["_id"] = result.inserted_id
        notify_for_type(
            NotificationType.BOOKING.value,
            title=f"Booking {document.get('booking_number')}",
            message="A new booking is waiting to be confirmed.",
            related_entity_type="bookings",
            related_entity_id=document["_id"],
            exclude_user_id=actor_id,
        )
        return self.get(document["_id"])

    def confirm(self, booking_id, *, actor_id) -> dict:
        document = self.get(booking_id)
        status = document.get("booking_status")
        if status == BookingStatus.CONFIRMED.value:
            self._ensure_invoice(document["_id"], actor_id=actor_id)
            return document
        if status == BookingStatus.CANCELLED.value:
            raise BusinessRuleViolation("A cancelled booking cannot be confirmed.")
        if status == BookingStatus.COMPLETED.value:
            raise BusinessRuleViolation("A completed booking cannot be confirmed again.")
        if status != BookingStatus.PENDING.value:
            raise BusinessRuleViolation("Only a pending booking can be confirmed.")
        self.tours.assert_ready_for_customer_bookings(document["tour_id"])
        count = int(document.get("travelers_count") or len(document.get("travelers") or []))
        self.tours.try_reserve_seats(document["tour_id"], count)
        now = utcnow()
        try:
            result = self.repository.update_if(
                document["_id"],
                expected={"booking_status": BookingStatus.PENDING.value},
                updates={"booking_status": BookingStatus.CONFIRMED.value, "updated_at": now},
            )
        except PyMongoError as extra:
            self.tours.release_reserved_seats(document["tour_id"], count)
            raise DatabaseUnavailableError("Could not confirm the booking.") from extra
        if result.matched_count != 1:
            self.tours.release_reserved_seats(document["tour_id"], count)
            current = self.get(document["_id"])
            if current.get("booking_status") == BookingStatus.CONFIRMED.value:
                return current
            raise BusinessRuleViolation("This booking could not be confirmed.")
        saved = self.get(document["_id"])
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.UPDATED.value,
            entity_type="bookings",
            entity_id=saved["_id"],
            description=f"Confirmed booking {saved.get('booking_number')}.",
            after={"booking_status": BookingStatus.CONFIRMED.value},
        )
        notify_for_type(
            NotificationType.BOOKING.value,
            title=f"Booking {saved.get('booking_number')}",
            message="Seats are confirmed. Time to brief the client.",
            related_entity_type="bookings",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        try:
            self._ensure_invoice(saved["_id"], actor_id=actor_id)
        except TourOpsError:
            self.repository.update_if(
                saved["_id"],
                expected={"booking_status": BookingStatus.CONFIRMED.value},
                updates={"booking_status": BookingStatus.PENDING.value, "updated_at": utcnow()},
            )
            self.tours.release_reserved_seats(document["tour_id"], count)
            raise
        return saved

    def cancel(self, booking_id, *, actor_id) -> dict:
        document = self.get(booking_id)
        status = document.get("booking_status")
        if status == BookingStatus.CANCELLED.value:
            return document
        if status not in {
            BookingStatus.PENDING.value,
            BookingStatus.CONFIRMED.value,
            BookingStatus.COMPLETED.value,
        }:
            raise BusinessRuleViolation("This booking cannot be cancelled.")
        self._close_finance_for_cancel(document, actor_id=actor_id)
        now = utcnow()
        try:
            result = self.repository.update_if(
                document["_id"],
                expected={"booking_status": status},
                updates={"booking_status": BookingStatus.CANCELLED.value, "updated_at": now},
            )
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not cancel the booking.") from extra
        if result.matched_count != 1:
            current = self.get(document["_id"])
            if current.get("booking_status") == BookingStatus.CANCELLED.value:
                return current
            raise BusinessRuleViolation("This booking could not be cancelled.")
        if status in {BookingStatus.CONFIRMED.value, BookingStatus.COMPLETED.value}:
            count = int(document.get("travelers_count") or len(document.get("travelers") or []))
            self.tours.release_reserved_seats(document["tour_id"], count)
        saved = self.get(document["_id"])
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.CANCELLED.value,
            entity_type="bookings",
            entity_id=saved["_id"],
            description=f"Cancelled booking {saved.get('booking_number')}.",
            after={"booking_status": BookingStatus.CANCELLED.value},
        )
        notify_for_type(
            NotificationType.BOOKING.value,
            title=f"Booking {saved.get('booking_number')}",
            message="This booking was cancelled. Check seats and any open invoice.",
            related_entity_type="bookings",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def complete(self, booking_id, *, actor_id) -> dict:
        document = self.get(booking_id)
        status = document.get("booking_status")
        if status == BookingStatus.COMPLETED.value:
            return document
        if status != BookingStatus.CONFIRMED.value:
            raise BusinessRuleViolation("Only a confirmed booking can be marked completed.")
        now = utcnow()
        try:
            result = self.repository.update_if(
                document["_id"],
                expected={"booking_status": BookingStatus.CONFIRMED.value},
                updates={"booking_status": BookingStatus.COMPLETED.value, "updated_at": now},
            )
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not complete the booking.") from extra
        if result.matched_count != 1:
            current = self.get(document["_id"])
            if current.get("booking_status") == BookingStatus.COMPLETED.value:
                return current
            raise BusinessRuleViolation("This booking could not be completed.")
        saved = self.get(document["_id"])
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.COMPLETED.value,
            entity_type="bookings",
            entity_id=saved["_id"],
            description=f"Completed booking {saved.get('booking_number')}.",
            after={"booking_status": BookingStatus.COMPLETED.value},
        )
        self._ensure_invoice(saved["_id"], actor_id=actor_id)
        return saved

    def _ensure_invoice(self, booking_id, *, actor_id) -> None:
        from apps.invoices.services import InvoiceService

        InvoiceService().create_for_booking(str(booking_id), created_by=str(actor_id))

    def _close_finance_for_cancel(self, document: dict, *, actor_id) -> None:
        from apps.invoices.services import InvoiceService

        invoice = InvoiceService().repository.find_by_booking(document["_id"])
        if not invoice:
            return
        paid = to_decimal(invoice.get("paid_amount") or 0)
        refunded = to_decimal(invoice.get("refunded_amount") or 0)
        if paid - refunded > ZERO:
            raise BusinessRuleViolation(
                "This booking still has unrefunded payments. Complete refunds before cancelling."
            )
        InvoiceService().cancel(invoice["_id"], actor_id=actor_id)

    def assign_rooms(self, booking_id, assignments: list[dict], *, actor_id, tour_id=None) -> dict:
        document = self.get(booking_id)
        if tour_id and str(document.get("tour_id")) != str(tour_id):
            raise ValidationError("Booking does not belong to this tour.")
        travelers = list(document.get("travelers") or [])
        for item in assignments:
            index = item.get("traveler_index", item.get("index"))
            try:
                index = int(index)
            except (TypeError, ValueError) as extra:
                raise ValidationError("Invalid traveler index.") from extra
            if index < 0 or index >= len(travelers):
                raise ValidationError("Traveler index is out of range.")
            person = dict(travelers[index])
            if "room_number" in item:
                person["room_number"] = (item.get("room_number") or "").strip() or None
            if "room_type" in item:
                person["room_type"] = (item.get("room_type") or "").strip().upper() or None
            if "hotel_reservation_id" in item:
                person["hotel_reservation_id"] = parse_optional_object_id(
                    item.get("hotel_reservation_id"), field="hotel_reservation_id"
                )
            travelers[index] = person
        try:
            self.repository.update(document["_id"], {"travelers": travelers, "updated_at": utcnow()})
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not save room assignments.") from extra
        return self.get(document["_id"])

    def _present(self, document: dict) -> dict:
        customer = None
        tour = None
        if document.get("customer_id"):
            customer = self.repository.find_customer(document["customer_id"])
        if document.get("tour_id"):
            tour = self.repository.find_tour(document["tour_id"])
        return present_booking(document, customer=customer, tour=tour)
