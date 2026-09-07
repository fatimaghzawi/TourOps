from bson import ObjectId
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.constants import AuditAction
from apps.audit.services import AuditService
from apps.notifications.constants import NotificationType
from apps.notifications.services import NotificationService, notify_for_type, roles_for_type
from apps.attachments.services import AttachmentService
from core.constants import AttachmentCategory, AttachmentEntityType, UserRole
from core.exceptions import NotFoundError, ValidationError


OWNER_ID = "000000000000000000000001"
ACCOUNTANT_ID = "000000000000000000000003"
AGENT_ID = "000000000000000000000002"


def _user(*, user_id, role, email):
    from apps.accounts.models import User

    User.objects.create_user(
        email=email,
        password="changeme1",
        first_name=role.title().split("_")[0],
        last_name="Staff",
        role=role,
        mongo_id=user_id,
        is_active=True,
    )


def test_audit_log_and_list_filters(db, fake_mongo):
    _user(user_id=OWNER_ID, role=UserRole.OWNER_ADMIN.value, email="owner@tourops.local")
    entity_id = ObjectId()
    saved = AuditService().log(
        actor_id=OWNER_ID,
        action=AuditAction.CREATED.value,
        entity_type="expenses",
        entity_id=entity_id,
        description="Created expense EXP-1001.",
    )
    assert saved["_id"]
    rows = AuditService().list_presented(entity_type="expenses", action=AuditAction.CREATED.value)
    assert len(rows) == 1
    assert rows[0]["action_label"] == "Created"
    assert rows[0]["who"]
    related = AuditService().for_entity("expenses", entity_id)
    assert related[0]["id"] == str(saved["_id"])
    detail = AuditService().get_presented(str(saved["_id"]))
    assert "EXP-1001" in detail["description"]


def test_audit_rejects_blank_description():
    try:
        AuditService().log(
            actor_id=OWNER_ID,
            action=AuditAction.CREATED.value,
            entity_type="expenses",
            entity_id=ObjectId(),
            description="  ",
        )
    except ValidationError:
        return
    raise AssertionError("expected ValidationError")


def test_notifications_create_mark_read_and_roles(db, fake_mongo):
    _user(user_id=OWNER_ID, role=UserRole.OWNER_ADMIN.value, email="owner@tourops.local")
    _user(user_id=ACCOUNTANT_ID, role=UserRole.ACCOUNTANT.value, email="accountant@tourops.local")
    service = NotificationService()
    created = service.create(
        user_id=OWNER_ID,
        type=NotificationType.EXPENSE.value,
        title="Expense EXP-1001",
        message="Office rent was recorded.",
        related_entity_type="expenses",
        related_entity_id=ObjectId(),
    )
    assert created["unread"] is True
    assert service.unread_count(OWNER_ID) == 1
    service.mark_read(created["id"], OWNER_ID)
    assert service.unread_count(OWNER_ID) == 0
    count = service.notify_roles(
        (UserRole.ACCOUNTANT.value, UserRole.OWNER_ADMIN.value),
        type=NotificationType.PAYMENT.value,
        title="Payment PAY-1",
        message="A customer payment was recorded.",
        exclude_user_id=OWNER_ID,
    )
    assert count == 1
    assert service.unread_count(ACCOUNTANT_ID) == 1
    assert service.mark_all_read(ACCOUNTANT_ID)["updated"] == 1
    assert service.unread_count(ACCOUNTANT_ID) == 0


def test_navbar_has_notifications_and_profile_menu(owner_session, fake_mongo):
    NotificationService().create(
        user_id=OWNER_ID,
        type=NotificationType.EXPENSE.value,
        title="Expense EXP-1001",
        message="Office rent was recorded.",
    )
    page = owner_session.get(reverse("dashboard:owner"))
    assert page.status_code == 200
    html = page.content
    assert b'<details class="nav-drop">' in html
    assert b'data-notes-toggle' in html
    assert b"Expense EXP-1001" in html
    assert b'data-profile-toggle' in html
    assert b"Change password" in html
    assert b"Log out" in html


def test_notification_html_and_api(owner_session, fake_mongo):
    item = NotificationService().create(
        user_id=OWNER_ID,
        type=NotificationType.EXPENSE.value,
        title="Expense EXP-1001",
        message="Office rent was recorded.",
    )
    listing = owner_session.get(reverse("notifications:list"))
    assert listing.status_code == 200
    assert b"Expense EXP-1001" in listing.content
    api = owner_session.get("/api/notifications/")
    assert api.status_code == 200
    assert api.json()["data"]["unread_count"] == 1
    marked = owner_session.post(f"/api/notifications/{item['id']}/read/")
    assert marked.status_code == 200
    assert owner_session.get("/api/notifications/").json()["data"]["unread_count"] == 0


def test_audit_html_and_api(owner_session, fake_mongo):
    saved = AuditService().log(
        actor_id=OWNER_ID,
        action=AuditAction.CREATED.value,
        entity_type="expenses",
        entity_id=ObjectId(),
        description="Created expense EXP-1001.",
    )
    page = owner_session.get(reverse("audit:list"))
    assert page.status_code == 200
    assert b"Created expense EXP-1001." in page.content
    api = owner_session.get("/api/audit/")
    assert api.status_code == 200
    assert len(api.json()["data"]["audit_logs"]) == 1
    detail = owner_session.get(f"/api/audit/{saved['_id']}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["action"] == AuditAction.CREATED.value


def test_agent_cannot_view_audit(agent_session):
    response = agent_session.get(reverse("audit:list"))
    assert response.status_code == 403
    api = agent_session.get("/api/audit/")
    assert api.status_code == 403


def test_attachment_upload_download_and_delete(owner_session, fake_mongo, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    entity_id = ObjectId()
    upload = SimpleUploadedFile("receipt.png", b"\x89PNG\r\n\x1a\nhello", content_type="image/png")
    created = AttachmentService().create(
        actor_id=OWNER_ID,
        entity_type=AttachmentEntityType.EXPENSES.value,
        entity_id=entity_id,
        category=AttachmentCategory.RECEIPT.value,
        upload=upload,
        notes="Hotel invoice",
    )
    presented = AttachmentService().get_presented(str(created["_id"]))
    assert presented["file_name"] == "receipt.png"
    listing = owner_session.get(reverse("attachments:list"))
    assert listing.status_code == 200
    assert b"receipt.png" in listing.content
    download = owner_session.get(reverse("attachments:download", args=[str(created["_id"])]))
    assert download.status_code == 200
    api = owner_session.get("/api/attachments/?entity_type=expenses")
    assert api.status_code == 200
    assert api.json()["data"]["attachments"][0]["id"] == str(created["_id"])
    deleted = owner_session.delete(f"/api/attachments/{created['_id']}/")
    assert deleted.status_code == 200
    try:
        AttachmentService().get(str(created["_id"]))
    except NotFoundError:
        return
    raise AssertionError("expected NotFoundError")


def test_attachment_rejects_empty_file(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    upload = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
    try:
        AttachmentService().create(
            actor_id=OWNER_ID,
            entity_type=AttachmentEntityType.EXPENSES.value,
            entity_id=ObjectId(),
            category=AttachmentCategory.RECEIPT.value,
            upload=upload,
        )
    except ValidationError:
        return
    raise AssertionError("expected ValidationError")


def test_expense_create_writes_audit_and_notifies(db, fake_mongo):
    _user(user_id=OWNER_ID, role=UserRole.OWNER_ADMIN.value, email="owner@tourops.local")
    _user(user_id=ACCOUNTANT_ID, role=UserRole.ACCOUNTANT.value, email="accountant@tourops.local")
    from tests.test_expenses import _create_general

    expense = _create_general()
    logs = AuditService().list_presented(entity_type="expenses")
    assert any("Created expense" in row["description"] for row in logs)
    inbox = NotificationService().list_for_user(ACCOUNTANT_ID)
    assert inbox
    assert inbox[0]["type"] == NotificationType.EXPENSE.value
    assert str(expense["_id"]) == inbox[0]["related_entity_id"]


def test_notify_for_type_routes_admin_accountant_and_agent(db, fake_mongo):
    _user(user_id=OWNER_ID, role=UserRole.OWNER_ADMIN.value, email="owner@tourops.local")
    _user(user_id=ACCOUNTANT_ID, role=UserRole.ACCOUNTANT.value, email="accountant@tourops.local")
    _user(user_id=AGENT_ID, role=UserRole.TRAVEL_AGENT.value, email="agent@tourops.local")
    assert roles_for_type(NotificationType.PAYMENT.value) == (
        UserRole.ACCOUNTANT.value,
        UserRole.OWNER_ADMIN.value,
    )
    assert roles_for_type(NotificationType.BOOKING.value) == (
        UserRole.TRAVEL_AGENT.value,
        UserRole.OWNER_ADMIN.value,
    )
    assert roles_for_type(NotificationType.ATTACHMENT.value, entity_type="tours") == (
        UserRole.TRAVEL_AGENT.value,
        UserRole.OWNER_ADMIN.value,
    )
    assert roles_for_type(NotificationType.ATTACHMENT.value, entity_type="expenses") == (
        UserRole.ACCOUNTANT.value,
        UserRole.OWNER_ADMIN.value,
    )
    booking_id = ObjectId()
    notify_for_type(
        NotificationType.BOOKING.value,
        title="Booking BK-1001",
        message="A new booking is waiting to be confirmed.",
        related_entity_type="bookings",
        related_entity_id=booking_id,
        exclude_user_id=OWNER_ID,
    )
    assert NotificationService().unread_count(AGENT_ID) == 1
    assert NotificationService().unread_count(ACCOUNTANT_ID) == 0
    notify_for_type(
        NotificationType.PAYMENT.value,
        title="Payment PAY-1001",
        message="A customer payment was recorded.",
        related_entity_type="payments",
        related_entity_id=ObjectId(),
        exclude_user_id=OWNER_ID,
    )
    assert NotificationService().unread_count(ACCOUNTANT_ID) == 1
    assert NotificationService().list_for_user(AGENT_ID)[0]["type"] == NotificationType.BOOKING.value
