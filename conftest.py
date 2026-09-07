from django.test import Client
import pytest
from apps.accounts.models import User
from core.constants import UserRole
from tests.fakes import FakeMongo


@pytest.fixture(autouse=True)
def fake_mongo(monkeypatch):
    mongo = FakeMongo()
    monkeypatch.setattr("core.database.get_collection", mongo.get_collection)
    monkeypatch.setattr("core.numbering.get_collection", mongo.get_collection)
    monkeypatch.setattr("core.indexes.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.presentation.story.get_collection", mongo.get_collection)
    monkeypatch.setattr(
        "apps.presentation.management.commands.seed_istanbul_escape.get_collection",
        mongo.get_collection,
    )
    monkeypatch.setattr("apps.accounts.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.accounts.settings_service.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.expenses.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.supplier_payments.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.reports.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.suppliers.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.suppliers.offering_repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.packages.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.tours.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.bookings.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.customers.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.supplier_reservations.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.invoices.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.invoices.services.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.audit.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.notifications.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.attachments.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.payments.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.payments.services.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.payments.views.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.receipts.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.receipts.views.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.refunds.repositories.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.refunds.services.get_collection", mongo.get_collection)
    monkeypatch.setattr("apps.refunds.views.get_collection", mongo.get_collection)
    return mongo


def _make_user(*, email, role, first_name, last_name, mongo_id, password="changeme1"):
    return User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        mongo_id=mongo_id,
        is_active=True,
    )


@pytest.fixture
def owner_user(db):
    return _make_user(
        email="owner@tourops.local",
        role=UserRole.OWNER_ADMIN.value,
        first_name="Owner",
        last_name="Admin",
        mongo_id="000000000000000000000001",
    )


@pytest.fixture
def agent_user(db):
    return _make_user(
        email="agent@tourops.local",
        role=UserRole.TRAVEL_AGENT.value,
        first_name="Amina",
        last_name="Agent",
        mongo_id="000000000000000000000002",
    )


@pytest.fixture
def accountant_user(db):
    return _make_user(
        email="accountant@tourops.local",
        role=UserRole.ACCOUNTANT.value,
        first_name="Karim",
        last_name="Books",
        mongo_id="000000000000000000000003",
    )


def _logged_in(user):
    session = Client()
    session.force_login(user)
    return session


@pytest.fixture
def owner_session(owner_user):
    return _logged_in(owner_user)


@pytest.fixture
def agent_session(agent_user):
    return _logged_in(agent_user)


@pytest.fixture
def accountant_session(accountant_user):
    return _logged_in(accountant_user)
