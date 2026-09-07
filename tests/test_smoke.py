import json

from django.urls import reverse

from core.responses import error_response, success_response


def test_mongodb_settings_are_loaded(settings):
    assert settings.MONGODB_URI
    assert settings.MONGODB_DB_NAME


def test_login_page_responds(client):
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 200
    assert b"TourOps" in response.content


def test_root_redirects(client):
    response = client.get("/", follow=False)
    assert response.status_code in {302, 301}


def test_customers_requires_login(client):
    response = client.get(reverse("customers:list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_api_requires_login(client):
    response = client.get("/api/customers/")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHENTICATED"


def test_api_customers_list_empty(owner_session):
    response = owner_session.get("/api/customers/")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["customers"] == []


def test_dashboard_routes_exist(owner_session):
    for name in ("dashboard:agent", "dashboard:accountant", "dashboard:owner"):
        response = owner_session.get(reverse(name))
        assert response.status_code == 200, name


def test_feature_html_routes_exist(owner_session):
    names = [
        "customers:list",
        "bookings:list",
        "tours:list",
        "packages:list",
        "suppliers:list",
        "suppliers:service_new",
        "packages:list",
        "invoices:list",
        "payments:list",
        "receipts:list",
        "refunds:list",
        "refunds:create",
        "expenses:list",
        "supplier_payments:list",
        "supplier_reservations:list",
        "finance:customer_balances",
        "reports:list",
        "notifications:list",
        "audit:list",
        "accounts:users",
        "accounts:settings",
        "availability:index",
    ]
    for name in names:
        response = owner_session.get(reverse(name))
        assert response.status_code == 200, name


def test_success_and_error_helpers():
    ok = success_response({"id": 1})
    assert ok.status_code == 200
    assert json.loads(ok.content) == {"success": True, "data": {"id": 1}}

    err = error_response("NOPE", "Broken", status=400)
    assert err.status_code == 400
    body = json.loads(err.content)
    assert body["success"] is False
    assert body["error"]["code"] == "NOPE"
