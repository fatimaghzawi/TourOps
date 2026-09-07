import json
from decimal import Decimal

from bson import ObjectId
from django.urls import reverse

from apps.expenses.services import ExpenseService
from apps.supplier_payments.services import SupplierPaymentService
from core.constants import ExpensePaymentStatus, PaymentMethod
from core.exceptions import NotFoundError, ValidationError
from core.money import ZERO, to_money
from tests.test_expenses import OWNER_ID, _create_general, _create_tour_expense, _insert_supplier


def _pay(expense, **overrides):
    payload = {
        "actor_id": OWNER_ID,
        "expense_id": expense["_id"],
        "amount": "1000.00",
        "payment_method": PaymentMethod.BANK_TRANSFER.value,
        "payment_date": "2026-08-20",
        "reference_number": "AP-4410",
    }
    payload.update(overrides)
    return SupplierPaymentService().create(**payload)


def test_payment_updates_expense_balance(fake_mongo):
    expense, _tour, supplier = _create_tour_expense(fake_mongo)
    payment = _pay(expense, amount="2000.00")
    assert payment["supplier_payment_number"] == "SP-1001"
    assert payment["supplier_id"] == supplier["_id"]
    updated = ExpenseService().get(expense["_id"])
    assert updated["payment_status"] == ExpensePaymentStatus.PARTIALLY_PAID.value
    assert to_money(updated["paid_amount"]) == Decimal("2000.00")
    assert to_money(updated["remaining_amount"]) == Decimal("1000.00")


def test_payment_can_settle_expense(fake_mongo):
    expense, _tour, _supplier = _create_tour_expense(fake_mongo)
    _pay(expense, amount="3000.00")
    updated = ExpenseService().get(expense["_id"])
    assert updated["payment_status"] == ExpensePaymentStatus.PAID.value
    assert to_money(updated["remaining_amount"]) == ZERO


def test_cannot_pay_more_than_remaining(fake_mongo):
    expense, _tour, _supplier = _create_tour_expense(fake_mongo)
    _pay(expense, amount="2500.00")
    try:
        _pay(expense, amount="600.00")
    except ValidationError as extra:
        assert "remaining" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_pay_expense_without_supplier():
    expense = _create_general()
    try:
        _pay(expense)
    except ValidationError as extra:
        assert "no supplier" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_nested_create_rejects_other_supplier(fake_mongo):
    expense, _tour, _supplier = _create_tour_expense(fake_mongo)
    other = _insert_supplier(fake_mongo, name="Other Co")
    try:
        SupplierPaymentService().create(
            actor_id=OWNER_ID,
            expense_id=expense["_id"],
            amount="100.00",
            payment_method=PaymentMethod.CASH.value,
            supplier_id=other["_id"],
        )
    except ValidationError as extra:
        assert "belong" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_void_restores_expense_balance(fake_mongo):
    expense, _tour, _supplier = _create_tour_expense(fake_mongo)
    payment = _pay(expense, amount="2000.00")
    SupplierPaymentService().void(payment["_id"], actor_id=OWNER_ID)
    updated = ExpenseService().get(expense["_id"])
    assert updated["payment_status"] == ExpensePaymentStatus.UNPAID.value
    assert to_money(updated["paid_amount"]) == ZERO
    try:
        SupplierPaymentService().get(payment["_id"])
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")
    assert SupplierPaymentService().list_items() == []


def test_agent_forbidden_from_supplier_payments(agent_session):
    assert agent_session.get(reverse("supplier_payments:list")).status_code == 403
    assert agent_session.get("/api/supplier-payments/").status_code == 403


def test_accountant_can_open_supplier_payments(accountant_session):
    response = accountant_session.get(reverse("supplier_payments:list"))
    assert response.status_code == 200
    assert b"No supplier payments yet" in response.content


def test_html_create_and_detail(owner_session, fake_mongo):
    expense, _tour, _supplier = _create_tour_expense(fake_mongo)
    response = owner_session.post(
        reverse("supplier_payments:create"),
        {
            "expense_id": str(expense["_id"]),
            "amount": "2000.00",
            "payment_method": PaymentMethod.BANK_TRANSFER.value,
            "payment_date": "2026-08-20",
            "reference_number": "AP-4410",
            "notes": "",
            "currency": "USD",
        },
    )
    assert response.status_code == 302, response.content
    payment = SupplierPaymentService().list_items()[0]
    assert payment["supplier_payment_number"] == "SP-1001"
    detail = owner_session.get(reverse("supplier_payments:detail", args=[str(payment["_id"])]))
    assert detail.status_code == 200
    assert b"SP-1001" in detail.content
    assert b"AP-4410" in detail.content
    listing = owner_session.get(reverse("supplier_payments:list"))
    assert b"SP-1001" in listing.content
    bill = ExpenseService().get(expense["_id"])
    assert to_money(bill["paid_amount"]) == Decimal("2000.00")


def test_html_unknown_id_redirects(owner_session):
    response = owner_session.get(reverse("supplier_payments:detail", args=["sp-1008"]))
    assert response.status_code == 302
    assert reverse("supplier_payments:list") in response["Location"]


def test_api_create_list_get_and_nested(owner_session, fake_mongo):
    expense, _tour, supplier = _create_tour_expense(fake_mongo)
    created = owner_session.post(
        "/api/supplier-payments/",
        data=json.dumps(
            {
                "expense_id": str(expense["_id"]),
                "amount": 1000,
                "method": "CASH",
                "payment_date": "2026-08-21",
                "ref": "AP-9",
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    body = created.json()["data"]
    assert body["number"] == "SP-1001"
    assert body["amount"] == "1000.00"
    payment_id = body["id"]

    listing = owner_session.get("/api/supplier-payments/")
    assert listing.status_code == 200
    assert len(listing.json()["data"]["payments"]) == 1

    detail = owner_session.get(f"/api/supplier-payments/{payment_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["ref"] == "AP-9"

    nested = owner_session.get(f"/api/suppliers/{supplier['_id']}/payments/")
    assert nested.status_code == 200
    assert nested.json()["data"]["payments"][0]["id"] == payment_id

    nested_create = owner_session.post(
        f"/api/suppliers/{supplier['_id']}/payments/",
        data=json.dumps(
            {
                "expense_id": str(expense["_id"]),
                "amount": "500.00",
                "payment_method": "BANK_TRANSFER",
            }
        ),
        content_type="application/json",
    )
    assert nested_create.status_code == 201, nested_create.content
    updated = ExpenseService().get(expense["_id"])
    assert to_money(updated["paid_amount"]) == Decimal("1500.00")

    voided = owner_session.post(f"/api/supplier-payments/{payment_id}/void/")
    assert voided.status_code == 200
    assert voided.json()["data"]["voided"] is True
    detail_after_void = owner_session.get(f"/api/supplier-payments/{payment_id}/")
    assert detail_after_void.status_code == 404


def test_api_nested_missing_supplier_is_404(owner_session):
    response = owner_session.get(f"/api/suppliers/{ObjectId()}/payments/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
