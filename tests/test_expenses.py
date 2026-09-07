import json
from datetime import timedelta
from decimal import Decimal

from bson import ObjectId
from django.urls import reverse

from apps.expenses.services import ExpenseService
from core.constants import ExpenseCategory, ExpensePaymentStatus, ExpenseScope
from core.exceptions import NotFoundError, ValidationError
from core.money import ZERO, to_money
from core.utils import utcnow


OWNER_ID = "000000000000000000000001"


def _insert_supplier(mongo, **overrides):
    doc = {
        "_id": ObjectId(),
        "supplier_number": f"SUP-{ObjectId()}",
        "name": "Nile View Hotel",
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    doc.update(overrides)
    mongo.get_collection("suppliers").insert_one(doc)
    return doc


def _insert_tour(mongo, **overrides):
    doc = {
        "_id": ObjectId(),
        "tour_code": f"TOUR-{ObjectId()}",
        "name": "Cairo Discovery",
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    doc.update(overrides)
    mongo.get_collection("tours").insert_one(doc)
    return doc


def _create_general(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "expense_scope": ExpenseScope.GENERAL.value,
        "category": ExpenseCategory.RENT.value,
        "amount": "1400.00",
        "description": "Office rent August",
        "expense_date": "2026-08-01",
        "due_date": "2026-08-01",
    }
    payload.update(overrides)
    return ExpenseService().create(**payload)


def _create_tour_expense(mongo, **overrides):
    tour = _insert_tour(mongo)
    supplier = _insert_supplier(mongo)
    payload = {
        "actor_id": OWNER_ID,
        "expense_scope": ExpenseScope.TOUR.value,
        "category": ExpenseCategory.HOTEL.value,
        "amount": "3000.00",
        "description": "Hotel block, Nile View",
        "expense_date": "2026-08-20",
        "due_date": "2026-09-10",
        "supplier_id": supplier["_id"],
        "tour_id": tour["_id"],
    }
    payload.update(overrides)
    expense = ExpenseService().create(**payload)
    return expense, tour, supplier


def test_create_general_expense_numbers_and_balances():
    expense = _create_general()
    assert expense["expense_number"] == "EXP-1001"
    assert expense["payment_status"] == ExpensePaymentStatus.UNPAID.value
    assert to_money(expense["amount"]) == Decimal("1400.00")
    assert to_money(expense["paid_amount"]) == ZERO
    assert to_money(expense["remaining_amount"]) == Decimal("1400.00")
    assert expense["tour_id"] is None


def test_create_tour_expense_requires_tour():
    try:
        ExpenseService().create(
            actor_id=OWNER_ID,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.HOTEL.value,
            amount="100",
            description="Rooms",
            expense_date="2026-08-01",
        )
    except ValidationError as exc:
        assert "tour" in exc.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_create_rejects_unknown_supplier(fake_mongo):
    try:
        ExpenseService().create(
            actor_id=OWNER_ID,
            expense_scope=ExpenseScope.GENERAL.value,
            category=ExpenseCategory.RENT.value,
            amount="100",
            description="Rent",
            expense_date="2026-08-01",
            supplier_id=str(ObjectId()),
        )
    except ValidationError as exc:
        assert "Supplier not found" in exc.message
    else:
        raise AssertionError("expected ValidationError")


def test_create_tour_expense_links_supplier_and_tour(fake_mongo):
    expense, tour, supplier = _create_tour_expense(fake_mongo)
    assert expense["tour_id"] == tour["_id"]
    assert expense["supplier_id"] == supplier["_id"]
    presented = ExpenseService().get_presented(expense["_id"])
    assert presented["supplier"] == "Nile View Hotel"
    assert presented["related"] == "Cairo Discovery"
    assert presented["number"] == "EXP-1001"


def test_list_filters_by_category(fake_mongo):
    _create_general()
    _create_tour_expense(fake_mongo)
    hotels = ExpenseService().list_presented(category=ExpenseCategory.HOTEL.value)
    rents = ExpenseService().list_presented(category=ExpenseCategory.RENT.value)
    assert len(hotels) == 1
    assert hotels[0]["category"] == ExpenseCategory.HOTEL.value
    assert len(rents) == 1
    assert rents[0]["category"] == ExpenseCategory.RENT.value


def test_update_description_and_amount():
    expense = _create_general()
    updated = ExpenseService().update(
        expense["_id"],
        description="Office rent September",
        amount="1500.00",
    )
    assert updated["description"] == "Office rent September"
    assert to_money(updated["amount"]) == Decimal("1500.00")
    assert to_money(updated["remaining_amount"]) == Decimal("1500.00")


def test_cannot_lower_amount_below_paid():
    expense = _create_general()
    ExpenseService().sync_paid_amount(expense["_id"], "800.00")
    try:
        ExpenseService().update(expense["_id"], amount="500.00")
    except ValidationError as extra:
        assert "already has supplier payments" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_sync_paid_amount_sets_partial_and_paid():
    expense = _create_general(amount="1000.00")
    partial = ExpenseService().sync_paid_amount(expense["_id"], "400.00")
    assert partial["payment_status"] == ExpensePaymentStatus.PARTIALLY_PAID.value
    assert to_money(partial["remaining_amount"]) == Decimal("600.00")
    paid = ExpenseService().sync_paid_amount(expense["_id"], "1000.00")
    assert paid["payment_status"] == ExpensePaymentStatus.PAID.value
    assert to_money(paid["remaining_amount"]) == ZERO


def test_cannot_delete_expense_with_payments():
    expense = _create_general()
    ExpenseService().sync_paid_amount(expense["_id"], "100.00")
    try:
        ExpenseService().soft_delete(expense["_id"], actor_id=OWNER_ID)
    except ValidationError as extra:
        assert "payments" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_soft_delete_hides_expense():
    expense = _create_general()
    ExpenseService().soft_delete(expense["_id"], actor_id=OWNER_ID)
    try:
        ExpenseService().get(expense["_id"])
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")
    assert ExpenseService().list_items() == []


def test_overdue_flag():
    expense = _create_general(due_date=(utcnow() - timedelta(days=3)).date().isoformat())
    presented = ExpenseService().get_presented(expense["_id"])
    assert presented["overdue"] is True
    paid = ExpenseService().sync_paid_amount(expense["_id"], expense["amount"])
    assert ExpenseService().get_presented(paid["_id"])["overdue"] is False


def test_list_for_tour_and_supplier(fake_mongo):
    expense, tour, supplier = _create_tour_expense(fake_mongo)
    _create_general()
    tour_rows = ExpenseService().list_for_tour(tour["_id"])
    supplier_rows = ExpenseService().list_for_supplier(supplier["_id"])
    assert len(tour_rows) == 1
    assert tour_rows[0]["id"] == str(expense["_id"])
    assert len(supplier_rows) == 1
    assert supplier_rows[0]["supplier_id"] == str(supplier["_id"])


def test_agent_forbidden_from_expenses(agent_session):
    assert agent_session.get(reverse("expenses:list")).status_code == 403
    assert agent_session.get("/api/expenses/").status_code == 403


def test_accountant_can_open_expenses(accountant_session):
    response = accountant_session.get(reverse("expenses:list"))
    assert response.status_code == 200
    assert b"No expenses yet" in response.content


def test_html_create_and_detail(owner_session, fake_mongo):
    response = owner_session.post(
        reverse("expenses:create"),
        {
            "expense_scope": ExpenseScope.GENERAL.value,
            "category": ExpenseCategory.SOFTWARE.value,
            "amount": "89.00",
            "currency": "USD",
            "description": "Accounting SaaS",
            "expense_date": "2026-08-12",
            "due_date": "2026-08-20",
            "receipt_file": "invoice-saas.pdf",
        },
    )
    assert response.status_code == 302
    expense = ExpenseService().list_items()[0]
    assert expense["expense_number"] == "EXP-1001"
    detail = owner_session.get(reverse("expenses:detail", args=[str(expense["_id"])]))
    assert detail.status_code == 200
    assert b"EXP-1001" in detail.content
    assert b"Accounting SaaS" in detail.content
    listing = owner_session.get(reverse("expenses:list"))
    assert b"EXP-1001" in listing.content


def test_html_unknown_id_redirects(owner_session):
    response = owner_session.get(reverse("expenses:detail", args=["exp-1041"]))
    assert response.status_code == 302
    assert reverse("expenses:list") in response["Location"]


def test_api_create_list_get_patch(owner_session, fake_mongo):
    tour = _insert_tour(fake_mongo)
    create = owner_session.post(
        "/api/expenses/",
        data=json.dumps(
            {
                "scope": "TOUR",
                "category": "MARKETING",
                "amount": 250,
                "description": "Nile felucca",
                "expense_date": "2026-08-22",
                "tour_id": str(tour["_id"]),
            }
        ),
        content_type="application/json",
    )
    assert create.status_code == 201, create.content
    body = create.json()
    assert body["success"] is True
    assert body["data"]["number"] == "EXP-1001"
    assert body["data"]["amount"] == "250.00"
    expense_id = body["data"]["id"]

    listing = owner_session.get("/api/expenses/")
    assert listing.status_code == 200
    assert len(listing.json()["data"]["expenses"]) == 1

    detail = owner_session.get(f"/api/expenses/{expense_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["description"] == "Nile felucca"

    patch = owner_session.patch(
        f"/api/expenses/{expense_id}/",
        data=json.dumps({"description": "Nile felucca sunset"}),
        content_type="application/json",
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["description"] == "Nile felucca sunset"

    nested = owner_session.get(f"/api/tours/{tour['_id']}/expenses/")
    assert nested.status_code == 200
    assert nested.json()["data"]["expenses"][0]["id"] == expense_id


def test_api_expenses_for_missing_tour_is_404(owner_session):
    response = owner_session.get(f"/api/tours/{ObjectId()}/expenses/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_api_rejects_invalid_json(owner_session):
    response = owner_session.post("/api/expenses/", data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
