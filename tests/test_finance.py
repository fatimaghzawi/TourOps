from bson import ObjectId

from tests.test_expenses import _create_general, _create_tour_expense
from tests.test_reports import _insert_booking, _insert_invoice


def test_finance_receivables_and_payables_are_live(owner_session, fake_mongo):
    _create_general()
    for url in ("/api/finance/receivables/", "/api/finance/payables/"):
        response = owner_session.get(url)
        assert response.status_code == 200, url
        assert response.json()["success"] is True


def test_supplier_and_customer_balances(owner_session, fake_mongo):
    expense, tour, supplier = _create_tour_expense(fake_mongo)
    supplier_balance = owner_session.get(f"/api/suppliers/{supplier['_id']}/balance/")
    assert supplier_balance.status_code == 200
    data = supplier_balance.json()["data"]
    assert data["supplier_id"] == str(supplier["_id"])
    assert data["outstanding"] == "3000.00"
    assert data["count"] == 1

    listing = owner_session.get("/api/finance/supplier-balances/")
    assert listing.status_code == 200
    assert listing.json()["data"]["count"] == 1

    booking = _insert_booking(fake_mongo, tour)
    invoice = _insert_invoice(fake_mongo, booking)
    customer_id = str(booking["customer_id"])
    customer_balance = owner_session.get(f"/api/customers/{customer_id}/balance/")
    assert customer_balance.status_code == 200
    body = customer_balance.json()["data"]
    assert body["customer_id"] == customer_id
    assert body["outstanding"] == "18000.00"
    assert body["count"] == 1
    assert body["invoices"][0]["id"] == str(invoice["_id"])

    customers = owner_session.get("/api/finance/customer-balances/")
    assert customers.status_code == 200
    assert customers.json()["data"]["count"] == 1


def test_tour_profitability_and_dashboards(owner_session, fake_mongo):
    _expense, tour, _supplier = _create_tour_expense(fake_mongo)
    _insert_booking(fake_mongo, tour)
    profitability = owner_session.get(f"/api/tours/{tour['_id']}/profitability/")
    assert profitability.status_code == 200
    assert profitability.json()["data"]["selected"]["id"] == str(tour["_id"])

    missing = owner_session.get(f"/api/tours/{ObjectId()}/profitability/")
    assert missing.status_code == 404

    accountant = owner_session.get("/api/dashboard/accountant/")
    assert accountant.status_code == 200
    assert "receivables" in accountant.json()["data"]
    assert "payables" in accountant.json()["data"]

    owner = owner_session.get("/api/dashboard/owner/")
    assert owner.status_code == 200
    assert "revenue" in owner.json()["data"]
    assert "profit" in owner.json()["data"]


def test_receipts_list_is_empty_until_payments(owner_session):
    response = owner_session.get("/api/receipts/")
    assert response.status_code == 200
    assert response.json()["data"]["receipts"] == []


def test_missing_supplier_balance_is_404(owner_session):
    response = owner_session.get(f"/api/suppliers/{ObjectId()}/balance/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
