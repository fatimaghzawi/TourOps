from __future__ import annotations

from apps.accounts.models import User
from apps.notifications.constants import TYPE_BADGE, TYPE_LABELS, NotificationType
from apps.notifications.repositories import NotificationRepository
from core.constants import UserRole
from core.exceptions import NotFoundError, ValidationError
from core.soft_delete import stamp_new
from core.utils import parse_object_id, serialize_id, utcnow


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _when_label(value) -> str:
    if value is None:
        return "Earlier"
    if hasattr(value, "strftime"):
        today = utcnow().date()
        day = value.date() if hasattr(value, "date") else value
        if day == today:
            return "Today"
        if (today - day).days == 1:
            return "Yesterday"
        return value.strftime("%d %b %Y")
    return "Earlier"


def present_notification(document: dict) -> dict:
    related = document.get("related_entity") or {}
    kind = document.get("type") or NotificationType.SYSTEM.value
    created = document.get("created_at")
    return {
        "id": serialize_id(document.get("_id")),
        "user_id": serialize_id(document.get("user_id")),
        "type": kind,
        "kind": kind,
        "type_label": TYPE_LABELS.get(kind, kind.replace("_", " ").title()),
        "badge": TYPE_BADGE.get(kind, "b-mute"),
        "title": document.get("title") or "",
        "message": document.get("message") or "",
        "body": document.get("message") or "",
        "is_read": bool(document.get("is_read")),
        "unread": not bool(document.get("is_read")),
        "when": _when_label(created),
        "time_display": created.strftime("%H:%M") if hasattr(created, "strftime") else "",
        "created_at": _iso(created),
        "related_entity_type": related.get("type") if isinstance(related, dict) else getattr(related, "type", None),
        "related_entity_id": serialize_id(related.get("id") if isinstance(related, dict) else getattr(related, "id", None)),
    }


class NotificationService:
    def __init__(self, repository: NotificationRepository | None = None):
        self.repository = repository or NotificationRepository()

    def create(
        self,
        *,
        user_id,
        type: str,
        title: str,
        message: str,
        related_entity_type: str | None = None,
        related_entity_id=None,
    ) -> dict:
        kind = (type or "").strip().lower()
        title = (title or "").strip()
        message = (message or "").strip()
        if kind not in TYPE_LABELS:
            raise ValidationError("Invalid notification type.")
        if not title:
            raise ValidationError("Title is required.")
        if not message:
            raise ValidationError("Message is required.")
        related = None
        if related_entity_type and related_entity_id is not None:
            related = {
                "type": related_entity_type,
                "id": parse_object_id(related_entity_id, field="related_entity_id"),
            }
        document = stamp_new(
            {
                "user_id": parse_object_id(user_id, field="user_id"),
                "type": kind,
                "title": title,
                "message": message,
                "related_entity": related,
                "is_read": False,
                "created_at": utcnow(),
            }
        )
        result = self.repository.insert(document)
        document["_id"] = result.inserted_id
        return present_notification(document)

    def list_for_user(self, user_id, **filters) -> list[dict]:
        return [present_notification(row) for row in self.repository.list_for_user(user_id, **filters)]

    def unread_count(self, user_id) -> int:
        return self.repository.count_unread(user_id)

    def get_for_user(self, doc_id: str, user_id) -> dict:
        document = self.repository.find_by_id(doc_id)
        if not document or serialize_id(document.get("user_id")) != str(user_id):
            raise NotFoundError("Notification not found.")
        return present_notification(document)

    def mark_read(self, doc_id: str, user_id) -> dict:
        matched = self.repository.mark_read(doc_id, user_id)
        if not matched:
            raise NotFoundError("Notification not found.")
        return self.get_for_user(doc_id, user_id)

    def mark_all_read(self, user_id) -> dict:
        updated = self.repository.mark_all_read(user_id)
        return {"updated": updated}

    def notify_roles(
        self,
        roles: tuple[str, ...] | list[str],
        *,
        type: str,
        title: str,
        message: str,
        related_entity_type: str | None = None,
        related_entity_id=None,
        exclude_user_id=None,
    ) -> int:
        allowed = {getattr(role, "value", role) for role in roles}
        exclude = str(exclude_user_id) if exclude_user_id is not None else None
        count = 0
        for user in User.objects.active_with_roles(allowed):
            if exclude and user.actor_id == exclude:
                continue
            self.create(
                user_id=user.actor_id,
                type=type,
                title=title,
                message=message,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
            )
            count += 1
        return count


def safe_notify_roles(roles, **kwargs) -> None:
    try:
        NotificationService().notify_roles(roles, **kwargs)
    except Exception:
        return


FINANCE_NOTIFY_ROLES = (UserRole.ACCOUNTANT.value, UserRole.OWNER_ADMIN.value)
OWNER_NOTIFY_ROLES = (UserRole.OWNER_ADMIN.value,)
AGENT_NOTIFY_ROLES = (UserRole.TRAVEL_AGENT.value,)
OPS_NOTIFY_ROLES = (UserRole.TRAVEL_AGENT.value, UserRole.OWNER_ADMIN.value)

TYPE_NOTIFY_ROLES = {
    NotificationType.PAYMENT.value: FINANCE_NOTIFY_ROLES,
    NotificationType.REFUND.value: FINANCE_NOTIFY_ROLES,
    NotificationType.EXPENSE.value: FINANCE_NOTIFY_ROLES,
    NotificationType.SUPPLIER.value: FINANCE_NOTIFY_ROLES,
    NotificationType.BOOKING.value: OPS_NOTIFY_ROLES,
    NotificationType.TOUR.value: OPS_NOTIFY_ROLES,
    NotificationType.SYSTEM.value: OWNER_NOTIFY_ROLES,
    NotificationType.ATTACHMENT.value: OPS_NOTIFY_ROLES,
}

FINANCE_ATTACHMENT_ENTITIES = {
    "expenses",
    "invoices",
    "payments",
    "refunds",
    "supplier_payments",
}


def roles_for_type(kind: str, *, entity_type: str | None = None) -> tuple[str, ...]:
    kind = (kind or "").strip().lower()
    if kind == NotificationType.ATTACHMENT.value and entity_type in FINANCE_ATTACHMENT_ENTITIES:
        return FINANCE_NOTIFY_ROLES
    return TYPE_NOTIFY_ROLES.get(kind, OWNER_NOTIFY_ROLES)


def notify_for_type(kind: str, **kwargs) -> None:
    roles = roles_for_type(kind, entity_type=kwargs.get("related_entity_type"))
    safe_notify_roles(roles, type=kind, **kwargs)
