import json
from decimal import Decimal

from django.urls import reverse

from apps.bookings.services import BookingService
from apps.customers.services import CustomerService
from apps.expenses.services import ExpenseService
from apps.finance.services import FinanceService
from apps.invoices.services import InvoiceService
from apps.packages.services import PackageService
from apps.payments.services import PaymentService
from apps.receipts.services import ReceiptService
from apps.refunds.services import RefundService
from apps.reports.services import ReportService
from apps.supplier_payments.services import SupplierPaymentService
from apps.tours.services import TourService
from core.constants import (
    BookingStatus,
    ExpenseCategory,
    ExpenseScope,
    InvoiceStatus,
    PaymentRecordStatus,
    RecordStatus,
    RefundPolicyTier,
    RefundStatus,
    SupplierReservationStatus,
    TourStatus,
)
from core.exceptions import BusinessRuleViolation, ValidationError
from core.money import ZERO, to_money
from tests.test_operations import OWNER_ID, _booking, _customer, _hotel, _hotel_reservation, _tour


def _invoice(booking):
    return InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)


def _pay(invoice, amount, *, method="CASH", reference=None):
    return PaymentService().record_for_invoice(
        invoice["id"],
        amount=amount,
        method=method,
        recorded_by=OWNER_ID,
        reference_number=reference,
    )


def _expect_rule(fn, fragment):
    try:
        fn()
    except BusinessRuleViolation as extra:
        assert fragment in extra.message.lower()
    else:
        raise AssertionError("expected BusinessRuleViolation")


def _expect_validation(fn, fragment):
    try:
        fn()
    except ValidationError as extra:
        assert fragment in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_confirm_booking_consumes_seats():
    tour = _tour(capacity=50)
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    assert booking["booking_status"] == BookingStatus.CONFIRMED.value
    assert TourService().get(tour["_id"])["booked_seats"] == 1


def test_booking_cannot_exceed_tour_capacity():
    tour = _tour(capacity=50)
    customer = _customer()
    first = _booking(tour, customer, ["Ada Lovelace"] * 49, confirm=True)
    assert first["booking_status"] == BookingStatus.CONFIRMED.value
    other = CustomerService().create(
        actor_id=OWNER_ID, first_name="Omar", last_name="Said", email="omar-seats@example.com"
    )
    waiting = _booking(tour, other, ["Omar Said", "Layla Said", "Nour Said"])
    _expect_rule(lambda: BookingService().confirm(waiting["_id"], actor_id=OWNER_ID), "seats")
    assert TourService().get(tour["_id"])["booked_seats"] == 49


def test_full_tour_rejects_one_more_seat():
    tour = _tour(capacity=50)
    customer = _customer()
    _booking(tour, customer, ["Traveler One"] * 50, confirm=True)
    other = CustomerService().create(
        actor_id=OWNER_ID, first_name="Late", last_name="Guest", email="late@example.com"
    )
    extra = _booking(tour, other, ["Late Guest"])
    _expect_rule(lambda: BookingService().confirm(extra["_id"], actor_id=OWNER_ID), "seats")
    assert TourService().get(tour["_id"])["booked_seats"] == 50


def test_confirmation_race_only_one_gets_last_seat():
    tour = _tour(capacity=1)
    a = _customer(email="agent-a@example.com")
    b = CustomerService().create(
        actor_id=OWNER_ID, first_name="Agent", last_name="Bee", email="agent-b@example.com"
    )
    booking_a = _booking(tour, a, ["Agent A"])
    booking_b = _booking(tour, b, ["Agent B"])
    BookingService().confirm(booking_a["_id"], actor_id=OWNER_ID)
    _expect_rule(lambda: BookingService().confirm(booking_b["_id"], actor_id=OWNER_ID), "seats")
    assert BookingService().get(booking_a["_id"])["booking_status"] == BookingStatus.CONFIRMED.value
    assert BookingService().get(booking_b["_id"])["booking_status"] == BookingStatus.PENDING.value
    assert TourService().get(tour["_id"])["booked_seats"] == 1


def test_cancelling_confirmed_booking_restores_seats():
    tour = _tour(capacity=10)
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi", "Waad Nasser"], confirm=True)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert TourService().get(tour["_id"])["booked_seats"] == 0
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.CANCELLED.value


def test_double_cancellation_does_not_restore_seats_twice():
    tour = _tour(capacity=5)
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    other = CustomerService().create(
        actor_id=OWNER_ID, first_name="Still", last_name="Going", email="still@example.com"
    )
    _booking(tour, other, ["Still Going"], confirm=True)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert TourService().get(tour["_id"])["booked_seats"] == 1


def test_cancelled_booking_cannot_be_confirmed():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    _expect_rule(lambda: BookingService().confirm(booking["_id"], actor_id=OWNER_ID), "cancelled")


def test_completed_booking_cannot_be_reopened():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    BookingService().complete(booking["_id"], actor_id=OWNER_ID)
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.COMPLETED.value
    _expect_rule(lambda: BookingService().confirm(booking["_id"], actor_id=OWNER_ID), "completed")


def test_pending_booking_cannot_be_completed():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    _expect_rule(lambda: BookingService().complete(booking["_id"], actor_id=OWNER_ID), "confirmed")


def test_cannot_book_cancelled_or_completed_tour():
    tour = _tour()
    TourService().update(tour["_id"], actor_id=OWNER_ID, status=TourStatus.CANCELLED.value)
    customer = _customer()
    _expect_rule(
        lambda: BookingService().create(
            actor_id=OWNER_ID,
            customer_id=customer["_id"],
            tour_id=tour["_id"],
            travelers=[{"first_name": "Fatima", "last_name": "Ghazzawi"}],
        ),
        "not open",
    )


def test_unpaid_invoice_is_cancelled_with_booking():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert InvoiceService().get(invoice["id"])["status"] == InvoiceStatus.CANCELLED.value
    assert TourService().get(tour["_id"])["booked_seats"] == 0


def test_paid_booking_cannot_cancel_until_refunded():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "400.00")
    _expect_rule(lambda: BookingService().cancel(booking["_id"], actor_id=OWNER_ID), "unrefunded")
    refund = RefundService().create_from_payment(
        payment["id"],
        reason="Customer cancelled",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="400.00",
        tier=RefundPolicyTier.AGENCY_CANCEL.value,
    )
    RefundService().approve(refund["id"], actor_id=OWNER_ID)
    RefundService().complete(refund["id"], actor_id=OWNER_ID)
    BookingService().cancel(booking["_id"], actor_id=OWNER_ID)
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.CANCELLED.value
    assert InvoiceService().get(invoice["id"])["status"] == InvoiceStatus.CANCELLED.value
    assert PaymentService().get(payment["id"])["status"] == PaymentRecordStatus.COMPLETED.value


def test_payment_cannot_exceed_invoice_remaining_amount():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "300.00")
    _pay(invoice, "500.00")
    rolled = InvoiceService().get(invoice["id"])
    assert rolled["status"] == InvoiceStatus.PARTIALLY_PAID.value
    assert to_money(rolled["remaining_amount"]) == Decimal("100.00")
    _expect_rule(lambda: _pay(invoice, "300.00"), "exceeds")
    _pay(invoice, "100.00")
    paid = InvoiceService().get(invoice["id"])
    assert paid["status"] == InvoiceStatus.PAID.value
    assert to_money(paid["remaining_amount"]) == ZERO
    saved = BookingService().get(booking["_id"])
    assert saved["booking_status"] == BookingStatus.COMPLETED.value
    assert saved["payment_status"] == "PAID"


def test_full_payment_blocks_cancel_until_refunded():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "900.00")
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.COMPLETED.value
    _expect_rule(lambda: BookingService().cancel(booking["_id"], actor_id=OWNER_ID), "unrefunded")


def test_payment_installments_reach_paid():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "300.00")
    assert to_money(InvoiceService().get(invoice["id"])["remaining_amount"]) == Decimal("600.00")
    _pay(invoice, "500.00")
    assert to_money(InvoiceService().get(invoice["id"])["remaining_amount"]) == Decimal("100.00")
    # remainder on a 900 invoice is 100, not 200; use a 1000 invoice via 2 travelers at 500? price is 900.
    # Keep 900: third payment is 100.
    _pay(invoice, "100.00")
    assert InvoiceService().get(invoice["id"])["status"] == InvoiceStatus.PAID.value
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.COMPLETED.value


def test_zero_and_negative_payments_are_rejected():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _expect_validation(lambda: _pay(invoice, "0"), "positive")
    _expect_validation(lambda: _pay(invoice, "-10"), "positive")


def test_cancelled_invoice_rejects_payment():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    InvoiceService().cancel(invoice["id"], actor_id=OWNER_ID)
    _expect_rule(lambda: _pay(invoice, "100.00"), "cancelled")
    rolled = InvoiceService().get(invoice["id"])
    assert rolled["status"] == InvoiceStatus.CANCELLED.value


def test_duplicate_payment_reference_is_idempotent():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    first = _pay(invoice, "300.00", reference="TRX-9")
    second = _pay(invoice, "300.00", reference="TRX-9")
    assert first["id"] == second["id"]
    assert to_money(InvoiceService().get(invoice["id"])["paid_amount"]) == Decimal("300.00")


def test_receipt_is_issued_once_per_payment():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "200.00")
    PaymentService()._issue_receipt(PaymentService().repository.find_by_id(payment["id"]))
    receipts = ReceiptService().list_items(payment_id=payment["id"])
    assert len(receipts) == 1


def test_refund_cannot_exceed_paid_amount():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    RefundService().create_from_payment(
        payment["id"],
        reason="Partial",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="200.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    _expect_rule(
        lambda: RefundService().create_from_payment(
            payment["id"],
            reason="Too much",
            refund_method="CASH",
            requested_by=OWNER_ID,
            amount="800.00",
            tier=RefundPolicyTier.OTHER.value,
        ),
        "remaining refundable",
    )


def test_zero_percent_tier_does_not_create_a_refund():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    _expect_validation(
        lambda: RefundService().create_from_payment(
            payment["id"],
            reason="Late cancel",
            refund_method="CASH",
            requested_by=OWNER_ID,
            tier=RefundPolicyTier.UNDER_7.value,
        ),
        "does not allow a refund",
    )


def test_voided_payment_cannot_be_refunded():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "400.00")
    PaymentService().void(payment["id"], actor_id=OWNER_ID)
    _expect_rule(
        lambda: RefundService().create_from_payment(
            payment["id"],
            reason="Mistake",
            refund_method="CASH",
            requested_by=OWNER_ID,
            amount="400.00",
            tier=RefundPolicyTier.AGENCY_CANCEL.value,
        ),
        "completed payment",
    )


def test_partial_then_full_refund_keeps_original_payment():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    first = RefundService().create_from_payment(
        payment["id"],
        reason="Partial",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="200.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    RefundService().approve(first["id"], actor_id=OWNER_ID)
    RefundService().complete(first["id"], actor_id=OWNER_ID)
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["refunded_amount"]) == Decimal("200.00")
    assert to_money(rolled["paid_amount"]) == Decimal("900.00")
    assert to_money(rolled["remaining_amount"]) == ZERO
    assert rolled["status"] == InvoiceStatus.PARTIALLY_REFUNDED.value
    second = RefundService().create_from_payment(
        payment["id"],
        reason="Remainder",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="700.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    RefundService().approve(second["id"], actor_id=OWNER_ID)
    RefundService().complete(second["id"], actor_id=OWNER_ID)
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["refunded_amount"]) == Decimal("900.00")
    assert PaymentService().get(payment["id"])["status"] == PaymentRecordStatus.COMPLETED.value


def test_customer_balance_comes_from_invoices():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    assert to_money(FinanceService().customer_balance(str(customer["_id"]))["outstanding"]) == Decimal("900.00")
    _pay(invoice, "400.00")
    assert to_money(FinanceService().customer_balance(str(customer["_id"]))["outstanding"]) == Decimal("500.00")
    _pay(invoice, "500.00")
    assert to_money(FinanceService().customer_balance(str(customer["_id"]))["outstanding"]) == ZERO


def test_supplier_payment_cannot_exceed_expense_balance(fake_mongo):
    tour = _tour()
    supplier = _hotel()
    expense = ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.HOTEL.value,
        amount="2000.00",
        description="Hotel block",
        expense_date="2026-08-20",
        supplier_id=supplier["_id"],
        tour_id=tour["_id"],
    )
    SupplierPaymentService().create(
        actor_id=OWNER_ID,
        expense_id=expense["_id"],
        amount="500.00",
        payment_method="BANK_TRANSFER",
    )
    remaining = ExpenseService().get(expense["_id"])
    assert to_money(remaining["remaining_amount"]) == Decimal("1500.00")
    SupplierPaymentService().create(
        actor_id=OWNER_ID,
        expense_id=expense["_id"],
        amount="1500.00",
        payment_method="BANK_TRANSFER",
    )
    settled = ExpenseService().get(expense["_id"])
    assert to_money(settled["remaining_amount"]) == ZERO
    _expect_validation(
        lambda: SupplierPaymentService().create(
            actor_id=OWNER_ID,
            expense_id=expense["_id"],
            amount="1.00",
            payment_method="CASH",
        ),
        "already paid",
    )


def test_hotel_expense_requires_supplier():
    tour = _tour()
    _expect_validation(
        lambda: ExpenseService().create(
            actor_id=OWNER_ID,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.HOTEL.value,
            amount="100.00",
            description="Rooms",
            expense_date="2026-08-01",
            tour_id=tour["_id"],
        ),
        "supplier",
    )


def test_cannot_post_expense_against_cancelled_tour():
    tour = _tour()
    TourService().update(tour["_id"], actor_id=OWNER_ID, status=TourStatus.CANCELLED.value)
    supplier = _hotel()
    _expect_rule(
        lambda: ExpenseService().create(
            actor_id=OWNER_ID,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.HOTEL.value,
            amount="100.00",
            description="Late hotel bill",
            expense_date="2026-08-01",
            tour_id=tour["_id"],
            supplier_id=supplier["_id"],
        ),
        "cancelled tour",
    )


def test_inactive_supplier_cannot_be_paid(fake_mongo):
    from apps.suppliers.services import SupplierService

    tour = _tour()
    supplier = _hotel()
    expense = ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.HOTEL.value,
        amount="500.00",
        description="Hotel",
        expense_date="2026-08-20",
        supplier_id=supplier["_id"],
        tour_id=tour["_id"],
    )
    SupplierService().update(supplier["_id"], actor_id=OWNER_ID, status=RecordStatus.INACTIVE.value)
    _expect_validation(
        lambda: SupplierPaymentService().create(
            actor_id=OWNER_ID,
            expense_id=expense["_id"],
            amount="100.00",
            payment_method="CASH",
        ),
        "inactive",
    )


def test_hotel_reservation_is_independent_of_tour_seats():
    tour = _tour(capacity=50)
    hotel = _hotel()
    reservation = _hotel_reservation(tour, hotel, status=SupplierReservationStatus.CONFIRMED.value)
    customer = _customer()
    _booking(tour, customer, ["Fatima Ghazzawi"] * 2, confirm=True)
    tour = TourService().get(tour["_id"])
    assert tour["capacity"] == 50
    assert tour["booked_seats"] == 2
    assert "room_allocations" not in reservation


def test_package_price_change_does_not_rewrite_existing_booking():
    package = PackageService().create(
        actor_id=OWNER_ID,
        name="Nile Classic",
        city="Cairo",
        country="Egypt",
        duration_days=6,
        selling_price_per_person="900.00",
        default_capacity=20,
    )
    tour = _tour(package_id=package["_id"], selling_price_per_person="900.00")
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    PackageService().update(package["_id"], actor_id=OWNER_ID, selling_price_per_person="1200.00")
    stored = BookingService().get(booking["_id"])
    assert to_money(stored["pricing"]["total_amount"]) == Decimal("900.00")


def test_tour_profitability_uses_invoices_minus_expenses():
    tour = _tour(selling_price_per_person="1000.00")
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"] * 10, confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "10000.00")
    supplier = _hotel()
    ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.HOTEL.value,
        amount="7000.00",
        description="Hotel block",
        expense_date="2026-09-12",
        supplier_id=supplier["_id"],
        tour_id=tour["_id"],
    )
    report = ReportService().tour_profitability({"tour_id": str(tour["_id"])})
    selected = report["selected"]
    assert to_money(selected["revenue"]) == Decimal("10000.00")
    assert to_money(selected["costs"]) == Decimal("7000.00")
    assert to_money(selected["profit"]) == Decimal("3000.00")


def test_loss_making_tour_with_no_bookings_is_negative():
    tour = _tour()
    supplier = _hotel()
    ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.HOTEL.value,
        amount="2000.00",
        description="Deposit",
        expense_date="2026-09-01",
        supplier_id=supplier["_id"],
        tour_id=tour["_id"],
    )
    report = ReportService().tour_profitability({"tour_id": str(tour["_id"])})
    selected = report["selected"]
    assert to_money(selected["revenue"]) == ZERO
    assert to_money(selected["profit"]) == Decimal("-2000.00")


def test_accounts_receivable_excludes_cancelled_invoices():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    InvoiceService().cancel(invoice["id"], actor_id=OWNER_ID)
    report = FinanceService().receivables()
    assert to_money(report["total"]) == ZERO


def test_agent_cannot_record_refund(agent_session):
    response = agent_session.post(
        "/api/refunds/",
        data=json.dumps({
            "payment_id": "000000000000000000000099",
            "reason": "Customer asked",
            "refund_method": "CASH",
            "amount": "100.00",
            "policy_tier": RefundPolicyTier.OTHER.value,
        }),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_agent_cannot_open_refund_form(agent_session):
    response = agent_session.get(reverse("refunds:create"))
    assert response.status_code == 403


def test_html_request_refund_from_payment(owner_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    page = owner_session.get(reverse("refunds:create") + f"?payment_id={payment['id']}")
    assert page.status_code == 200
    assert b"Issue refund" in page.content
    assert b"Refund now" in page.content
    assert payment["payment_number"].encode() in page.content
    posted = owner_session.post(
        reverse("refunds:create"),
        data={
            "payment_id": payment["id"],
            "policy_tier": RefundPolicyTier.AGENCY_CANCEL.value,
            "refund_method": "CASH",
            "reason": "Customer cancelled",
        },
    )
    assert posted.status_code == 302
    detail = owner_session.get(posted.url)
    assert detail.status_code == 200
    assert b"Customer cancelled" in detail.content
    assert b"Completed" in detail.content
    listed = owner_session.get(reverse("refunds:list"))
    assert b"Customer cancelled" in listed.content
    payment_page = owner_session.get(reverse("payments:detail", args=[payment["id"]]))
    assert b"Issue refund" in payment_page.content
    assert b"Refunds" in payment_page.content
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["refunded_amount"]) == Decimal("900.00")


def test_html_accountant_requests_refund_for_approval(accountant_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    page = accountant_session.get(reverse("refunds:create") + f"?payment_id={payment['id']}")
    assert page.status_code == 200
    assert b"Request refund" in page.content
    posted = accountant_session.post(
        reverse("refunds:create"),
        data={
            "payment_id": payment["id"],
            "policy_tier": RefundPolicyTier.AGENCY_CANCEL.value,
            "refund_method": "CASH",
            "reason": "Needs owner sign-off",
        },
    )
    assert posted.status_code == 302
    refunds = RefundService().list_items()
    assert refunds[0]["status"] == RefundStatus.PENDING.value
    assert to_money(InvoiceService().get(invoice["id"])["refunded_amount"]) == ZERO
    detail = accountant_session.get(posted.url)
    assert b"Needs owner sign-off" in detail.content
    assert b">Approve<" not in detail.content
    refund_id = refunds[0]["id"]
    blocked = accountant_session.post(reverse("refunds:approve", args=[refund_id]))
    assert blocked.status_code == 403
    assert RefundService().list_items()[0]["status"] == RefundStatus.PENDING.value


def test_accountant_cannot_confirm_booking(accountant_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    response = accountant_session.post(f"/api/bookings/{booking['_id']}/confirm/")
    assert response.status_code == 403
    assert BookingService().get(booking["_id"])["booking_status"] == BookingStatus.PENDING.value


def test_unauthenticated_cannot_open_booking_detail(client):
    response = client.get("/bookings/000000000000000000000099/")
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_agent_can_open_any_agency_booking(agent_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"])
    response = agent_session.get(reverse("bookings:detail", args=[str(booking["_id"])]))
    assert response.status_code == 200


def test_paid_invoice_cannot_be_cancelled_without_refund():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "100.00")
    _expect_rule(lambda: InvoiceService().cancel(invoice["id"], actor_id=OWNER_ID), "refund")


def test_confirm_issues_invoice():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoices = InvoiceService().list_items(booking_id=str(booking["_id"]))
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"].startswith("INV-")
    again = InvoiceService().create_for_booking(str(booking["_id"]), created_by=OWNER_ID)
    assert again["id"] == invoices[0]["id"]


def test_agent_collects_payment_on_booking(agent_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = InvoiceService().list_items(booking_id=str(booking["_id"]))[0]
    response = agent_session.post(
        reverse("bookings:pay", args=[str(booking["_id"])]),
        {
            "amount": invoice["remaining_amount"],
            "method": "CASH",
            "reference_number": "DESK-1",
        },
    )
    assert response.status_code == 302
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["remaining_amount"]) == ZERO
    assert agent_session.get(reverse("invoices:list")).status_code == 403
    payment = PaymentService().for_invoice(invoice["id"])[0]
    receipt = ReceiptService().for_payment(payment["id"])
    assert agent_session.get(reverse("receipts:detail", args=[receipt["id"]])).status_code == 200
    assert agent_session.get(reverse("receipts:list")).status_code == 403


def test_accountant_can_open_customer_detail_not_list(accountant_session):
    customer = _customer()
    assert accountant_session.get(reverse("customers:list")).status_code == 403
    assert accountant_session.get(reverse("customers:detail", args=[str(customer["_id"])])).status_code == 200


def test_accountant_records_payment_from_invoice(accountant_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    page = accountant_session.get(reverse("invoices:detail", args=[invoice["id"]]))
    assert page.status_code == 200
    assert b"Record payment" in page.content
    assert b">Customers</span>" not in page.content
    assert b">Bookings</span>" not in page.content
    response = accountant_session.post(
        reverse("invoices:pay", args=[invoice["id"]]),
        {"amount": "100.00", "method": "CASH", "reference_number": "AR-1"},
    )
    assert response.status_code == 302
    rolled = InvoiceService().get(invoice["id"])
    assert to_money(rolled["paid_amount"]) == Decimal("100.00")


def test_receivables_page_links_pay(accountant_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    page = accountant_session.get(reverse("finance:receivables"))
    assert page.status_code == 200
    assert invoice["invoice_number"].encode() in page.content
    assert b"Pay" in page.content


def test_refund_does_not_reopen_receivable():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    RefundService().create_from_payment(
        payment["id"],
        reason="Keep the booking, return part of the cash",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="200.00",
        tier=RefundPolicyTier.OTHER.value,
        direct=True,
    )
    rolled = InvoiceService().get(invoice["id"])
    assert rolled["status"] == InvoiceStatus.PARTIALLY_REFUNDED.value
    assert to_money(rolled["remaining_amount"]) == ZERO
    assert to_money(FinanceService().customer_balance(str(customer["_id"]))["outstanding"]) == ZERO
    report = ReportService().receivables()
    assert all(row["id"] != invoice["id"] for row in report.get("invoices") or [])


def test_second_refund_cannot_overdraw_same_payment():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    RefundService().create_from_payment(
        payment["id"],
        reason="First",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="900.00",
        tier=RefundPolicyTier.AGENCY_CANCEL.value,
    )
    _expect_rule(
        lambda: RefundService().create_from_payment(
            payment["id"],
            reason="Second",
            refund_method="CASH",
            requested_by=OWNER_ID,
            amount="900.00",
            tier=RefundPolicyTier.AGENCY_CANCEL.value,
        ),
        "remaining refundable",
    )


def test_cannot_cancel_tour_with_live_bookings():
    tour = _tour()
    customer = _customer()
    _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    _expect_rule(
        lambda: TourService().update(tour["_id"], actor_id=OWNER_ID, status=TourStatus.CANCELLED.value),
        "bookings",
    )


def test_double_click_payment_without_reference_is_idempotent():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    first = _pay(invoice, "300.00")
    second = _pay(invoice, "300.00")
    assert first["id"] == second["id"]
    assert to_money(InvoiceService().get(invoice["id"])["paid_amount"]) == Decimal("300.00")


def test_unpaid_invoice_can_be_reissued():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    replacement = InvoiceService().reissue(invoice["id"], actor_id=OWNER_ID)
    assert replacement["id"] != invoice["id"]
    assert InvoiceService().get(invoice["id"])["status"] == InvoiceStatus.CANCELLED.value
    assert replacement["status"] == InvoiceStatus.ISSUED.value
    assert to_money(replacement["total_amount"]) == to_money(invoice["total_amount"])


def test_paid_invoice_cannot_be_reissued_until_refunded():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    _pay(invoice, "900.00")
    _expect_rule(lambda: InvoiceService().reissue(invoice["id"], actor_id=OWNER_ID), "refund")
