import json

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.accounts.services import AuthService, UserService
from core.constants import UserRole, UserStatus
from core.exceptions import ValidationError


def _create_user(**overrides):
    payload = {
        "first_name": "Owner",
        "last_name": "Admin",
        "email": "owner@tourops.local",
        "password": "changeme1",
        "role": UserRole.OWNER_ADMIN.value,
        "phone": None,
    }
    payload.update(overrides)
    return UserService().create_user(**payload)


def test_authenticate_accepts_valid_credentials(db):
    created = _create_user()
    user = AuthService().authenticate("owner@tourops.local", "changeme1")
    assert user.actor_id == created["_id"]
    assert user.email == "owner@tourops.local"


def test_authenticate_rejects_bad_password(db):
    _create_user()
    try:
        AuthService().authenticate("owner@tourops.local", "wrong-password")
    except ValidationError as extra:
        assert "Invalid email or password" in extra.message
    else:
        raise AssertionError("expected ValidationError")


def test_authenticate_rejects_inactive_user(db):
    created = _create_user(email="agent@tourops.local", role=UserRole.TRAVEL_AGENT.value)
    owner = _create_user()
    UserService().set_status(created["_id"], UserStatus.INACTIVE.value, actor_id=owner["_id"])
    try:
        AuthService().authenticate("agent@tourops.local", "changeme1")
    except Exception as extra:
        assert "inactive" in str(extra).lower()
    else:
        raise AssertionError("expected inactive rejection")


def test_create_user_rejects_duplicate_email(db):
    _create_user()
    try:
        _create_user()
    except ValidationError as extra:
        assert "already exists" in extra.message
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_deactivate_self(db):
    owner = _create_user()
    try:
        UserService().set_status(owner["_id"], UserStatus.INACTIVE.value, actor_id=owner["_id"])
    except ValidationError as extra:
        assert "own account" in extra.message
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_deactivate_last_owner(db):
    owner = _create_user()
    agent = _create_user(
        first_name="Amina",
        last_name="Agent",
        email="agent@tourops.local",
        role=UserRole.TRAVEL_AGENT.value,
    )
    try:
        UserService().set_status(owner["_id"], UserStatus.INACTIVE.value, actor_id=agent["_id"])
    except ValidationError as extra:
        assert "last Owner" in extra.message
    else:
        raise AssertionError("expected ValidationError")


def test_password_is_hashed(db):
    user = _create_user()
    stored = User.objects.get(email="owner@tourops.local")
    assert stored.password != "changeme1"
    assert "pbkdf2" in stored.password
    assert stored.mongo_id == user["_id"]


def test_login_page_and_success(client, db):
    _create_user()
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 200
    assert b"Welcome back" in response.content
    assert b"Forgot password?" in response.content
    response = client.post(
        reverse("accounts:login"),
        {"email": "owner@tourops.local", "password": "changeme1"},
    )
    assert response.status_code == 302
    assert reverse("dashboard:owner") in response["Location"]


def test_password_reset_sends_token_email(client, db):
    _create_user()
    response = client.get(reverse("accounts:password_reset"))
    assert response.status_code == 200
    assert b"Reset password" in response.content
    response = client.post(
        reverse("accounts:password_reset"),
        {"email": "owner@tourops.local"},
    )
    assert response.status_code == 302
    assert reverse("accounts:password_reset_done") in response["Location"]
    assert len(mail.outbox) == 1
    user = User.objects.get(email="owner@tourops.local")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirm_url = reverse("accounts:password_reset_confirm", args=[uid, token])
    confirm = client.get(confirm_url)
    assert confirm.status_code in {200, 302}
    post_url = confirm["Location"] if confirm.status_code == 302 else confirm_url
    response = client.post(
        post_url,
        {"new_password1": "newpass99", "new_password2": "newpass99"},
    )
    assert response.status_code in {200, 302}
    AuthService().authenticate("owner@tourops.local", "newpass99")


def test_api_password_reset_does_not_set_password(client, db):
    _create_user()
    response = client.post(
        "/api/auth/password/reset/",
        data=json.dumps({"email": "owner@tourops.local", "password": "apireset99"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    AuthService().authenticate("owner@tourops.local", "changeme1")
    try:
        AuthService().authenticate("owner@tourops.local", "apireset99")
    except ValidationError:
        return
    raise AssertionError("API reset must not set the password directly")


def test_login_rejects_open_redirect(client, db):
    _create_user()
    response = client.post(
        reverse("accounts:login") + "?next=https://evil.example/phish",
        {"email": "owner@tourops.local", "password": "changeme1"},
    )
    assert response.status_code == 302
    assert "evil.example" not in response["Location"]
    assert reverse("dashboard:owner") in response["Location"]


def test_agent_cannot_open_invoices(agent_session):
    assert agent_session.get(reverse("invoices:list")).status_code == 403


def test_accountant_cannot_open_customers(accountant_session):
    assert accountant_session.get(reverse("customers:list")).status_code == 403


def test_agent_can_open_customers(agent_session):
    assert agent_session.get(reverse("customers:list")).status_code == 200


def test_accountant_can_open_invoices(accountant_session):
    response = accountant_session.get(reverse("invoices:list"))
    assert response.status_code == 200
    assert b">Customers</span>" not in response.content
    assert b">Bookings</span>" not in response.content
    assert b">Invoices</span>" in response.content


def test_agent_forbidden_from_users(agent_session):
    assert agent_session.get(reverse("accounts:users")).status_code == 403


def test_owner_can_create_user(owner_session):
    response = owner_session.post(
        reverse("accounts:user_create"),
        {
            "first_name": "Nour",
            "last_name": "Saleh",
            "email": "nour@tourops.local",
            "phone": "",
            "role": UserRole.TRAVEL_AGENT.value,
            "password": "secretpass",
            "confirm_password": "secretpass",
        },
    )
    assert response.status_code == 302
    users = UserService().list_users()
    assert any(row["email"] == "nour@tourops.local" for row in users)


def test_logout_post_clears_session(owner_session):
    response = owner_session.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
    follow = owner_session.get(reverse("customers:list"))
    assert follow.status_code == 302


def test_api_login_and_me(client, db):
    _create_user()
    response = client.post(
        "/api/auth/login/",
        data=json.dumps({"email": "owner@tourops.local", "password": "changeme1"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["role"] == UserRole.OWNER_ADMIN.value
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "owner@tourops.local"


def test_api_agent_forbidden_from_invoices(agent_session):
    response = agent_session.get("/api/invoices/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_api_accountant_forbidden_from_customers(accountant_session):
    response = accountant_session.get("/api/customers/")
    assert response.status_code == 403


def test_api_owner_lists_customers(owner_session):
    response = owner_session.get("/api/customers/")
    assert response.status_code == 200
    assert response.json()["success"] is True


def _settings_payload(**overrides):
    from apps.accounts.settings_service import PREFIX_SPECS
    from core.constants import DEFAULT_CURRENCY, DEFAULT_TAX_NAME, NUMBER_START

    payload = {
        "agency_name": "TourOps",
        "legal_name": "",
        "agency_email": "",
        "agency_phone": "",
        "agency_address": "",
        "currency": DEFAULT_CURRENCY,
        "tax_name": DEFAULT_TAX_NAME,
        "tax_rate": "0.00",
        "tax_enabled": "on",
        "invoice_due_days": "14",
        "number_start": str(NUMBER_START),
    }
    for key, _label, default in PREFIX_SPECS:
        payload[f"prefix_{key}"] = default
    payload.update(overrides)
    return payload


def test_owner_can_open_settings(owner_session):
    response = owner_session.get(reverse("accounts:settings"))
    assert response.status_code == 200
    assert b"Save settings" in response.content
    assert b'name="agency_name"' in response.content


def test_agent_cannot_open_settings(agent_session):
    assert agent_session.get(reverse("accounts:settings")).status_code == 403


def test_accountant_cannot_open_settings(accountant_session):
    assert accountant_session.get(reverse("accounts:settings")).status_code == 403


def test_owner_can_save_settings(owner_session):
    from core.constants import Collections
    from core.numbering import next_number

    posted = owner_session.post(
        reverse("accounts:settings"),
        _settings_payload(agency_name="Nile Voyages", prefix_bookings="BOOK"),
    )
    assert posted.status_code == 302
    saved = owner_session.get(reverse("accounts:settings"))
    assert saved.status_code == 200
    body = saved.content.decode()
    assert "Nile Voyages" in body
    assert 'value="BOOK"' in body
    assert saved.context["brand"]["name"] == "Nile Voyages"
    assert next_number(Collections.BOOKINGS) == "BOOK-1001"


def test_numbering_uses_defaults_without_saved_settings():
    from core.constants import Collections
    from core.numbering import next_number

    assert next_number(Collections.BOOKINGS) == "BK-1001"


def test_owner_can_open_django_admin(owner_session):
    response = owner_session.get("/admin/")
    assert response.status_code == 200


def test_agent_cannot_open_django_admin(agent_session):
    response = agent_session.get("/admin/")
    assert response.status_code in {302, 403}


def test_corrupt_session_is_cleared(client, db):
    session = client.session
    session["_auth_user_id"] = "999999"
    session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    response = client.get(reverse("customers:list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_deactivated_user_is_logged_out(client, db):
    created = _create_user(
        email="agent-kick@tourops.local",
        role=UserRole.TRAVEL_AGENT.value,
        first_name="Amina",
        last_name="Agent",
    )
    owner = _create_user()
    logged_in = client.post(
        reverse("accounts:login"),
        {"email": "agent-kick@tourops.local", "password": "changeme1"},
    )
    assert logged_in.status_code == 302
    assert client.get(reverse("customers:list")).status_code == 200
    UserService().set_status(created["id"], UserStatus.INACTIVE.value, actor_id=owner["id"])
    blocked = client.get(reverse("customers:list"))
    assert blocked.status_code == 302
    assert reverse("accounts:login") in blocked["Location"]


def test_seed_demo_user_refuses_when_debug_is_false(settings, db):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.DEBUG = False
    try:
        call_command("seed_demo_user")
    except CommandError as extra:
        assert "DEBUG" in str(extra)
    else:
        raise AssertionError("expected CommandError")


def test_login_locks_after_repeated_failures(db):
    from django.core.cache import cache

    from core.exceptions import PermissionDeniedError

    cache.clear()
    _create_user(email="lockout@tourops.local")
    for _ in range(8):
        try:
            AuthService().authenticate("lockout@tourops.local", "wrong-password", ip="10.0.0.9")
        except ValidationError:
            pass
        else:
            raise AssertionError("expected ValidationError")
    try:
        AuthService().authenticate("lockout@tourops.local", "changeme1", ip="10.0.0.9")
    except PermissionDeniedError as extra:
        assert "Too many" in extra.message
    else:
        raise AssertionError("expected lockout")
