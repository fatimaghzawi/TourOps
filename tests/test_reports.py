from datetime import datetime, timezone
from decimal import Decimal

from bson import ObjectId
from django.urls import reverse

from apps.expenses.services import ExpenseService
from apps.reports.services import ReportService
from apps.supplier_payments.services import SupplierPaymentService
from core.constants import (
    BookingStatus,
    ExpenseCategory,
    ExpenseScope,
    InvoiceStatus,
    PaymentMethod,
    PaymentRecordStatus,
    RefundStatus,
)
from core.money import to_money
from tests.test_expenses import OWNER_ID, _create_general, _create_tour_expense, _insert_tour


def _insert_booking(mongo, tour, *, total="18000.00", status=None):
    doc = {
        "_id": ObjectId(),
        "booking_number": "BK-1048",
        "customer_id": ObjectId(),
        "tour_id": tour["_id"],
        "booking_status": status or BookingStatus.CONFIRMED.value,
        "booking_date": datetime(2026, 8, 10, tzinfo=timezone.utc),
        "pricing": {"total_amount": total},
        "is_deleted": False,
    }
    mongo.get_collection("bookings").insert_one(doc)
    return doc


def _insert_invoice(mongo, booking, *, total="18000.00", remaining="18000.00", status=None):
    doc = {
        "_id": ObjectId(),
        "invoice_number": "INV-1042",
        "booking_id": booking["_id"],
        "customer_id": booking["customer_id"],
        "issue_date": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "due_date": datetime(2026, 9, 12, tzinfo=timezone.utc),
        "total_amount": total,
        "paid_amount": "0.00",
        "remaining_amount": remaining,
        "status": status or InvoiceStatus.ISSUED.value,
        "is_deleted": False,
    }
    mongo.get_collection("invoices").insert_one(doc)
    return doc


def _insert_payment(mongo, booking, *, amount="5000.00"):
    doc = {
        "_id": ObjectId(),
        "payment_number": "PAY-1042",
        "invoice_id": ObjectId(),
        "booking_id": booking["_id"],
        "customer_id": booking["customer_id"],
        "amount": amount,
        "currency": "USD",
        "payment_method": PaymentMethod.CARD.value,
        "payment_date": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "status": PaymentRecordStatus.COMPLETED.value,
        "reference_number": "CH-1",
        "is_deleted": False,
    }
    mongo.get_collection("payments").insert_one(doc)
    return doc


def test_expense_breakdown_groups_categories(fake_mongo):
    _create_general()
    _create_tour_expense(fake_mongo)
    report = ReportService().expense_breakdown()
    labels = {row["label"]: row["amount"] for row in report["groups"]}
    assert labels["Hotel"] == Decimal("3000.00")
    assert labels["Overhead"] == Decimal("1400.00")
    assert report["total"] == Decimal("4400.00")


def test_payables_only_includes_open_balances(fake_mongo):
    expense, _tour, supplier = _create_tour_expense(fake_mongo)
    _create_general(amount="100.00")
    SupplierPaymentService().create(
        actor_id=OWNER_ID,
        expense_id=expense["_id"],
        amount="3000.00",
        payment_method=PaymentMethod.CASH.value,
    )
    report = ReportService().payables()
    assert report["count"] == 1
    assert report["expenses"][0]["category"] == ExpenseCategory.RENT.value
    assert to_money(report["total"]) == Decimal("100.00")


def test_month_filter_excludes_other_months(fake_mongo):
    _create_general()
    august = ReportService().expense_breakdown({"month": "2026-08"})
    july = ReportService().expense_breakdown({"month": "2026-07"})
    assert august["total"] == Decimal("1400.00")
    assert july["total"] == Decimal("0.00")
    assert july["count"] == 0


def test_revenue_falls_back_to_bookings_without_invoices(fake_mongo):
    tour = _insert_tour(fake_mongo)
    _insert_booking(mongo=fake_mongo, tour=tour, total="18000.00")
    ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.MARKETING.value,
        amount="3000.00",
        description="Hotel",
        expense_date="2026-08-20",
        tour_id=tour["_id"],
    )
    report = ReportService().revenue()
    assert report["revenue"] == Decimal("18000.00")
    assert report["costs"] == Decimal("3000.00")
    assert report["profit"] == Decimal("15000.00")


def test_revenue_uses_invoices_when_present(fake_mongo):
    tour = _insert_tour(fake_mongo)
    booking = _insert_booking(mongo=fake_mongo, tour=tour, total="99999.00")
    _insert_invoice(mongo=fake_mongo, booking=booking, total="18000.00")
    report = ReportService().revenue()
    assert report["revenue"] == Decimal("18000.00")


def test_cash_flow_counts_payments_and_supplier_payments(fake_mongo):
    expense, tour, _supplier = _create_tour_expense(fake_mongo)
    booking = _insert_booking(mongo=fake_mongo, tour=tour)
    _insert_payment(mongo=fake_mongo, booking=booking, amount="5000.00")
    SupplierPaymentService().create(
        actor_id=OWNER_ID,
        expense_id=expense["_id"],
        amount="2000.00",
        payment_method=PaymentMethod.BANK_TRANSFER.value,
        payment_date="2026-08-20",
    )
    report = ReportService().profit_loss()
    assert report["money_in"] == Decimal("5000.00")
    assert report["money_out"] == Decimal("2000.00")
    assert report["net"] == Decimal("3000.00")


def test_tour_profitability_uses_expense_and_booking(fake_mongo):
    expense, tour, _supplier = _create_tour_expense(fake_mongo)
    _insert_booking(mongo=fake_mongo, tour=tour, total="10000.00")
    report = ReportService().tour_profitability()
    assert len(report["tours"]) == 1
    row = report["tours"][0]
    assert row["id"] == str(tour["_id"])
    assert row["revenue"] == Decimal("10000.00")
    assert row["supplier_costs"] == Decimal("3000.00")
    assert row["profit"] == Decimal("7000.00")
    assert row["margin"] == 70.0
    selected = ReportService().tour_profitability({"tour": str(tour["_id"])})
    assert selected["selected"]["name"] == "Cairo Discovery"


def test_receivables_and_transactions(fake_mongo):
    tour = _insert_tour(fake_mongo)
    booking = _insert_booking(mongo=fake_mongo, tour=tour)
    _insert_invoice(mongo=fake_mongo, booking=booking, remaining="1200.00")
    _insert_payment(mongo=fake_mongo, booking=booking, amount="800.00")
    ar = ReportService().receivables()
    assert ar["count"] == 1
    assert ar["total"] == Decimal("1200.00")
    ledger = ReportService().transactions()
    assert ledger["count"] == 1
    assert ledger["money_in"] == Decimal("800.00")
    refunds = ReportService().refunds()
    assert refunds["count"] == 0


def test_agent_forbidden_from_reports(agent_session):
    assert agent_session.get(reverse("reports:list")).status_code == 403
    assert agent_session.get("/api/reports/expenses/").status_code == 403


def test_accountant_can_open_report_pages(accountant_session):
    for name in (
        "reports:list",
        "reports:expenses",
        "reports:revenue",
        "reports:profit_loss",
        "reports:profitability",
        "reports:payments",
        "reports:refunds",
        "reports:transactions",
        "finance:receivables",
        "finance:payables",
        "finance:customer_balances",
        "finance:supplier_balances",
        "dashboard:accountant",
    ):
        assert accountant_session.get(reverse(name)).status_code == 200


def test_api_report_endpoints(owner_session, fake_mongo):
    _create_general()
    endpoints = [
        "/api/reports/expenses/",
        "/api/reports/revenue/",
        "/api/reports/payments/",
        "/api/reports/refunds/",
        "/api/reports/receivables/",
        "/api/reports/payables/",
        "/api/reports/tour-profitability/",
        "/api/reports/profit-loss/",
        "/api/reports/transactions/",
    ]
    for url in endpoints:
        response = owner_session.get(url)
        assert response.status_code == 200, url
        body = response.json()
        assert body["success"] is True
    breakdown = owner_session.get("/api/reports/expenses/").json()["data"]
    assert breakdown["total"] == "1400.00"
    assert breakdown["groups"][0]["label"] == "Overhead"


def test_html_expense_breakdown_renders_totals(owner_session, fake_mongo):
    _create_general()
    response = owner_session.get(reverse("reports:expenses"))
    assert response.status_code == 200
    assert b"Overhead" in response.content
    assert b"$1,400" in response.content


def test_html_business_finance_and_reports_hub(owner_session, fake_mongo):
    expense, _tour, supplier = _create_tour_expense(fake_mongo)
    payables = owner_session.get(reverse("finance:payables"))
    assert payables.status_code == 200
    assert expense["expense_number"].encode() in payables.content
    assert b"Business finance" in payables.content or b"Accounts payable" in payables.content

    balances = owner_session.get(reverse("finance:supplier_balances"))
    assert balances.status_code == 200
    assert supplier["name"].encode() in balances.content

    hub = owner_session.get(reverse("reports:list"))
    assert hub.status_code == 200
    assert b"Transactions" in hub.content
    assert b"Financial Reports" in hub.content
    assert b"logo-dark.png" in hub.content

    owner = owner_session.get(reverse("dashboard:owner"))
    assert owner.status_code == 200
    assert b"Receivables" in owner.content
    assert b"Tour profitability" in owner.content

    accountant = owner_session.get(reverse("dashboard:accountant"))
    assert accountant.status_code == 200
    assert b"Receivables" in accountant.content
    assert b"Business finance" in accountant.content
