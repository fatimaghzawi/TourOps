import json
from decimal import Decimal

from django.urls import reverse

from apps.bookings.services import BookingService
from apps.customers.services import CustomerService
from apps.invoices.services import InvoiceService
from apps.supplier_reservations.services import SupplierReservationService
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from apps.packages.services import PackageService
from apps.tours.services import TourService
from core.constants import BookingStatus, SupplierReservationStatus, SupplierServiceKind, SupplierType
from core.exceptions import BusinessRuleViolation
from core.money import to_money


OWNER_ID = "000000000000000000000001"


def _package(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Egypt Discovery",
        "city": "Cairo",
        "country": "Egypt",
        "duration_days": 7,
        "selling_price_per_person": "900.00",
        "default_capacity": 50,
    }
    payload.update(overrides)
    return PackageService().create(**payload)


def _tour(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Egypt Discovery",
        "city": "Cairo",
        "country": "Egypt",
        "start_date": "2026-09-12",
        "end_date": "2026-09-18",
        "capacity": 50,
        "selling_price_per_person": "900.00",
    }
    payload.update(overrides)
    if "package_id" not in payload:
        payload["package_id"] = _package()["_id"]
    return TourService().create(**payload)


def _hotel(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Nile View Hotel",
        "supplier_type": SupplierType.HOTEL.value,
        "email": "stay@nileview.example",
        "city": "Cairo",
        "country": "Egypt",
    }
    payload.update(overrides)
    return SupplierService().create(**payload)


def _second_hotel():
    return _hotel(name="Pyramids Hotel", email="stay@pyramids.example")


def _customer(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "first_name": "Fatima",
        "last_name": "Ghazzawi",
        "email": "fatima@example.com",
        "phone": "+20 100 000 0000",
        "city": "Cairo",
        "country": "Egypt",
    }
    payload.update(overrides)
    return CustomerService().create(**payload)


def _travelers(*names):
    people = []
    for name in names:
        first, last = name.split(" ", 1)
        people.append({"first_name": first, "last_name": last, "passport_number": f"P-{first[:2].upper()}1"})
    return people


def _booking(tour, customer, names, *, confirm=False):
    booking = BookingService().create(
        actor_id=OWNER_ID,
        customer_id=tour and customer["_id"],
        tour_id=tour["_id"],
        travelers=_travelers(*names),
    )
    if confirm:
        booking = BookingService().confirm(booking["_id"], actor_id=OWNER_ID)
    return booking


def _hotel_reservation(tour, hotel, *, status="REQUESTED", confirmation="NV-4410"):
    return SupplierReservationService().create(
        actor_id=OWNER_ID,
        tour_id=tour["_id"],
        supplier_id=hotel["_id"],
        status=status,
        confirmation_number=confirmation if status == SupplierReservationStatus.CONFIRMED.value else None,
        release_date="2026-09-01",
    )


def test_booking_blocked_until_planned_suppliers_confirm():
    hotel = _hotel()
    stay = SupplierOfferingService().create(
        actor_id=OWNER_ID,
        supplier_id=hotel["_id"],
        name="Nile stay",
        service_kind=SupplierServiceKind.ACCOMMODATION.value,
        estimated_cost="400.00",
    )
    package = _package(services=[{"supplier_service_id": stay["_id"]}])
    tour = _tour(package_id=package["_id"], capacity=10)
    customer = _customer()
    try:
        _booking(tour, customer, ["Fatima Ghazzawi"])
    except BusinessRuleViolation as extra:
        assert "supplier" in extra.message.lower()
    else:
        raise AssertionError("expected BusinessRuleViolation")
    reservation = _hotel_reservation(tour, hotel)
    try:
        _booking(tour, customer, ["Fatima Ghazzawi"])
    except BusinessRuleViolation as extra:
        assert "supplier" in extra.message.lower()
    else:
        raise AssertionError("expected BusinessRuleViolation")
    SupplierReservationService().confirm(
        reservation["_id"],
        actor_id=OWNER_ID,
        confirmation_number="NV-READY",
    )
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    assert booking["booking_status"] == BookingStatus.CONFIRMED.value


def test_confirm_booking_uses_tour_seats_not_rooms():
    tour = _tour(capacity=4)
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi", "Waad Nasser"], confirm=True)
    tour = TourService().get(tour["_id"])
    assert booking["booking_status"] == BookingStatus.CONFIRMED.value
    assert tour["booked_seats"] == 2
    assert tour["capacity"] == 4


def test_confirm_refuses_over_capacity():
    tour = _tour(capacity=2)
    customer = _customer()
    _booking(tour, customer, ["Fatima Ghazzawi", "Waad Nasser"], confirm=True)
    other = CustomerService().create(
        actor_id=OWNER_ID, first_name="Omar", last_name="Said", email="omar@example.com"
    )
    booking = _booking(tour, other, ["Omar Said"])
    try:
        BookingService().confirm(booking["_id"], actor_id=OWNER_ID)
    except BusinessRuleViolation as extra:
        assert "seats" in extra.message.lower()
    else:
        raise AssertionError("expected BusinessRuleViolation")
    assert TourService().get(tour["_id"])["booked_seats"] == 2


def test_cancel_confirmed_booking_restores_seats():
    tour = _tour(capacity=10)
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi", "Waad Nasser"], confirm=True)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert TourService().get(tour["_id"])["booked_seats"] == 0
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.CANCELLED.value


def test_cancel_pending_does_not_change_seats():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert TourService().get(tour["_id"])["booked_seats"] == 0


def test_invoice_only_after_confirm():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    try:
        InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    except BusinessRuleViolation:
        pass
    else:
        raise AssertionError("expected BusinessRuleViolation")
    BookingService().confirm(booking["_id"], actor_id=OWNER_ID)
    invoice = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    assert invoice["invoice_number"].startswith("INV-")
    assert to_money(invoice["total_amount"]) == Decimal("900.00")


def test_payment_creates_receipt_and_updates_invoice():
    from apps.payments.services import PaymentService
    from apps.receipts.services import ReceiptService
    from core.constants import PaymentStatus

    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    payment = PaymentService().record_for_invoice(
        invoice["id"],
        amount="400.00",
        method="CASH",
        recorded_by=OWNER_ID,
        reference_number="TRX-1",
    )
    assert payment["payment_number"].startswith("PAY-")
    rolled = InvoiceService().get(invoice["id"])
    assert rolled["status"] == "PARTIALLY_PAID"
    assert to_money(rolled["paid_amount"]) == Decimal("400.00")
    receipt = ReceiptService().for_payment(payment["id"])
    assert receipt["receipt_number"].startswith("REC-")
    booking = BookingService().get(booking["_id"])
    assert booking["payment_status"] == PaymentStatus.PARTIALLY_PAID.value

    PaymentService().record_for_invoice(
        invoice["id"],
        amount="500.00",
        method="BANK_TRANSFER",
        recorded_by=OWNER_ID,
    )
    rolled = InvoiceService().get(invoice["id"])
    assert rolled["status"] == "PAID"
    assert to_money(rolled["remaining_amount"]) == Decimal("0.00")
    booking = BookingService().get(booking["_id"])
    assert booking["payment_status"] == PaymentStatus.PAID.value
    assert booking["booking_status"] == BookingStatus.COMPLETED.value


def test_payment_cannot_exceed_remaining_balance():
    from apps.payments.services import PaymentService

    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    try:
        PaymentService().record_for_invoice(
            invoice["id"],
            amount="9999.00",
            method="CASH",
            recorded_by=OWNER_ID,
        )
    except BusinessRuleViolation as extra:
        assert "exceeds" in extra.message.lower()
    else:
        raise AssertionError("expected BusinessRuleViolation")


def test_refund_lifecycle_updates_invoice():
    from apps.payments.services import PaymentService
    from apps.refunds.services import RefundService
    from core.constants import RefundPolicyTier, RefundStatus

    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    payment = PaymentService().record_for_invoice(
        invoice["id"],
        amount="900.00",
        method="CASH",
        recorded_by=OWNER_ID,
    )
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.COMPLETED.value
    refund = RefundService().create_from_payment(
        payment["id"],
        reason="Customer cancelled",
        refund_method="CASH",
        requested_by=OWNER_ID,
        tier=RefundPolicyTier.DAYS_15_TO_29.value,
    )
    assert refund["status"] == RefundStatus.PENDING.value
    RefundService().approve(refund["id"], actor_id=OWNER_ID)
    completed = RefundService().complete(refund["id"], actor_id=OWNER_ID)
    assert completed["status"] == RefundStatus.COMPLETED.value
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["refunded_amount"]) > 0
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.CONFIRMED.value


def test_owner_direct_refund_skips_approval():
    from apps.payments.services import PaymentService
    from apps.refunds.services import RefundService
    from core.constants import RefundPolicyTier, RefundStatus

    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    payment = PaymentService().record_for_invoice(
        invoice["id"],
        amount="900.00",
        method="CASH",
        recorded_by=OWNER_ID,
    )
    refund = RefundService().create_from_payment(
        payment["id"],
        reason="Owner payout",
        refund_method="CASH",
        requested_by=OWNER_ID,
        tier=RefundPolicyTier.AGENCY_CANCEL.value,
        direct=True,
    )
    assert refund["status"] == RefundStatus.COMPLETED.value
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["refunded_amount"]) == Decimal("900.00")
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.CONFIRMED.value


def test_hotel_reservation_does_not_use_tour_seats():
    tour = _tour()
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel)
    presented = SupplierReservationService().get_presented(reservation["_id"])
    assert "room_count" not in presented
    assert "room_allocations" not in presented
    assert TourService().get(tour["_id"])["capacity"] == 50
    assert TourService().get(tour["_id"])["booked_seats"] == 0


def test_multiple_hotels_on_one_tour():
    tour = _tour()
    first = _hotel()
    second = _second_hotel()
    _hotel_reservation(tour, first)
    _hotel_reservation(tour, second)
    rows = SupplierReservationService().list_for_tour(tour["_id"])
    assert len(rows) == 2
    snapshot = SupplierReservationService().accommodation_snapshot(tour["_id"])
    assert len(snapshot["hotels"]) == 2
    assert "room_count" not in snapshot


def test_reservation_does_not_create_expense():
    tour = _tour()
    hotel = _hotel()
    _hotel_reservation(tour, hotel, status=SupplierReservationStatus.CONFIRMED.value)
    from core.database import get_collection
    from core.constants import Collections

    assert get_collection(Collections.EXPENSES).count_documents({}) == 0
    assert get_collection(Collections.SUPPLIER_PAYMENTS).count_documents({}) == 0


def test_html_reservation_pages(owner_session):
    tour = _tour()
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel)
    response = owner_session.get(reverse("tours:detail", args=[str(tour["_id"])]) + "?tab=reservations")
    assert response.status_code == 200
    assert b"Arrange supplier" in response.content
    response = owner_session.get(reverse("supplier_reservations:detail", args=[str(reservation["_id"])]))
    assert response.status_code == 200
    assert b"Nile View Hotel" in response.content
    assert b"Rooming list" not in response.content


def test_hotel_reservation_does_not_require_allocation():
    tour = _tour()
    hotel = _hotel()
    reservation = SupplierReservationService().create(
        actor_id=OWNER_ID,
        tour_id=tour["_id"],
        supplier_id=hotel["_id"],
    )
    assert reservation["service_type"] == "HOTEL"
    assert "room_allocations" not in reservation


def test_api_create_and_confirm_reservation(owner_session):
    tour = _tour()
    hotel = _hotel()
    create = owner_session.post(
        reverse("tours_api:reservations", args=[str(tour["_id"])]),
        data=json.dumps(
            {
                "supplier_id": str(hotel["_id"]),
            }
        ),
        content_type="application/json",
    )
    assert create.status_code == 201, create.content
    reservation_id = create.json()["data"]["id"]
    confirm = owner_session.post(
        reverse("supplier_reservations_api:confirm", args=[reservation_id]),
        data=json.dumps({"confirmation_number": "NV-4410"}),
        content_type="application/json",
    )
    assert confirm.status_code == 200
    assert confirm.json()["data"]["status"] == SupplierReservationStatus.CONFIRMED.value


def test_email_generation_uses_live_reservation_data():
    from apps.supplier_reservations.emails import SupplierEmailService

    tour = _tour(name="Egypt Explorer")
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel)
    email = SupplierEmailService().build_reservation_request(str(reservation["_id"]))
    presented = SupplierReservationService().get_presented(reservation["_id"])
    assert email["to"] == "stay@nileview.example"
    assert "Egypt Explorer" in email["subject"]
    assert "Nile View Hotel" in email["body"]
    assert "Twin" not in email["body"]
    assert "Occupancy" not in email["body"]
    assert "Sleeping capacity" not in email["body"]
    followup = SupplierEmailService().build_confirmation_followup(str(reservation["_id"]))
    assert presented["number"] in followup["subject"]
    assert presented["number"] in followup["body"]


def test_html_email_preview_and_ops_pages(owner_session):
    tour = _tour()
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel)
    email_page = owner_session.get(reverse("supplier_reservations:email", args=[str(reservation["_id"])]))
    assert email_page.status_code == 200
    assert b"stay@nileview.example" in email_page.content
    assert b"Egypt Discovery" in email_page.content
    agent_dash = owner_session.get(reverse("dashboard:agent"))
    assert agent_dash.status_code == 200
    assert b"Requested" in agent_dash.content


def test_accountant_cannot_open_supplier_reservations(accountant_session):
    assert accountant_session.get(reverse("supplier_reservations:list")).status_code == 403
    assert accountant_session.get(reverse("expenses:list")).status_code == 200


def test_agent_can_open_reservations_not_expenses(agent_session):
    assert agent_session.get(reverse("supplier_reservations:list")).status_code == 200
    assert agent_session.get(reverse("expenses:list")).status_code == 403


def test_html_confirm_does_not_create_expense_or_change_seats(owner_session):
    tour = _tour(capacity=10)
    customer = _customer()
    _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel)
    before = TourService().get(tour["_id"])["booked_seats"]
    missing = owner_session.post(
        reverse("supplier_reservations:confirm", args=[str(reservation["_id"])]),
        {},
    )
    assert missing.status_code == 302
    assert SupplierReservationService().get_presented(reservation["_id"])["status"] == SupplierReservationStatus.REQUESTED.value
    response = owner_session.post(
        reverse("supplier_reservations:confirm", args=[str(reservation["_id"])]),
        {"confirmation_number": "NVH-7821"},
    )
    assert response.status_code == 302
    presented = SupplierReservationService().get_presented(reservation["_id"])
    assert presented["status"] == SupplierReservationStatus.CONFIRMED.value
    assert presented["confirmation_number"] == "NVH-7821"
    assert TourService().get(tour["_id"])["booked_seats"] == before
    from core.constants import Collections
    from core.database import get_collection

    assert get_collection(Collections.EXPENSES).count_documents({}) == 0


def test_html_cancel_does_not_change_seats(owner_session):
    tour = _tour(capacity=10)
    customer = _customer()
    _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel, status=SupplierReservationStatus.CONFIRMED.value)
    before = TourService().get(tour["_id"])["booked_seats"]
    response = owner_session.post(reverse("supplier_reservations:cancel", args=[str(reservation["_id"])]))
    assert response.status_code == 302
    assert SupplierReservationService().get_presented(reservation["_id"])["status"] == SupplierReservationStatus.CANCELLED.value
    assert TourService().get(tour["_id"])["booked_seats"] == before
