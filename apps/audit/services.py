from __future__ import annotations

from apps.accounts.models import User
from apps.audit.constants import ACTION_BADGE, ACTION_LABELS, ENTITY_LABELS
from apps.audit.repositories import AuditLogRepository
from core.exceptions import NotFoundError, ValidationError
from core.utils import full_name, parse_object_id, serialize_id, utcnow


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _display_when(value) -> tuple[str, str]:
    if value is None:
        return "—", "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y"), value.strftime("%H:%M")
    text = str(value)
    return text, ""


def present_audit(document: dict, *, actor: dict | None = None) -> dict:
    created = document.get("created_at")
    date_label, time_label = _display_when(created)
    name = full_name((actor or {}).get("first_name"), (actor or {}).get("last_name")) or (
        (actor or {}).get("email") if actor else None
    ) or "System"
    action = document.get("action") or ""
    return {
        "id": serialize_id(document.get("_id")),
        "user_id": serialize_id(document.get("user_id")),
        "who": name,
        "action": action,
        "action_label": ACTION_LABELS.get(action, action.replace("_", " ").title()),
        "action_badge": ACTION_BADGE.get(action, "b-mute"),
        "entity_type": document.get("entity_type") or "",
        "entity_label": ENTITY_LABELS.get(document.get("entity_type") or "", (document.get("entity_type") or "").replace("_", " ").title()),
        "entity_id": serialize_id(document.get("entity_id")),
        "entity": f"{document.get('entity_type')}:{serialize_id(document.get('entity_id'))}",
        "description": document.get("description") or "",
        "related": document.get("description") or "",
        "date": date_label,
        "time": time_label,
        "created_at": _iso(created),
        "ip_address": document.get("ip_address"),
        "before": document.get("before"),
        "after": document.get("after"),
    }


class AuditService:
    def __init__(self, repository: AuditLogRepository | None = None):
        self.repository = repository or AuditLogRepository()

    def _actor(self, actor_id) -> dict | None:
        user = User.objects.by_actor_id(actor_id)
        return user.as_actor_dict() if user else None

    def log(
        self,
        *,
        actor_id,
        action: str,
        entity_type: str,
        entity_id,
        description: str,
        before: dict | None = None,
        after: dict | None = None,
        ip_address: str | None = None,
    ) -> dict:
        action = (action or "").strip().upper()
        entity_type = (entity_type or "").strip()
        description = (description or "").strip()
        if not action:
            raise ValidationError("Audit action is required.")
        if not entity_type:
            raise ValidationError("Entity type is required.")
        if not description:
            raise ValidationError("Description is required.")
        document = {
            "user_id": parse_object_id(actor_id, field="user_id"),
            "action": action,
            "entity_type": entity_type,
            "entity_id": parse_object_id(entity_id, field="entity_id"),
            "description": description,
            "before": before,
            "after": after,
            "ip_address": ip_address,
            "created_at": utcnow(),
        }
        result = self.repository.insert(document)
        document["_id"] = result.inserted_id
        return document

    def list_presented(self, **filters) -> list[dict]:
        rows = self.repository.find_all(**filters)
        cache: dict[str, dict | None] = {}
        presented = []
        for row in rows:
            key = serialize_id(row.get("user_id")) or ""
            if key not in cache:
                cache[key] = self._actor(key) if key else None
            presented.append(present_audit(row, actor=cache[key]))
        return presented

    def get_presented(self, doc_id: str) -> dict:
        document = self.repository.find_by_id(doc_id)
        if not document:
            raise NotFoundError("Audit log not found.")
        actor = self._actor(document.get("user_id")) if document.get("user_id") else None
        return present_audit(document, actor=actor)

    def for_entity(self, entity_type: str, entity_id, *, limit: int = 50) -> list[dict]:
        rows = self.repository.find_for_entity(entity_type, entity_id, limit=limit)
        cache: dict[str, dict | None] = {}
        presented = []
        for row in rows:
            key = serialize_id(row.get("user_id")) or ""
            if key not in cache:
                cache[key] = self._actor(key) if key else None
            presented.append(present_audit(row, actor=cache[key]))
        return presented


def safe_audit(**kwargs) -> None:
    """Best-effort audit write — never breaks the business mutation."""
    try:
        AuditService().log(**kwargs)
    except Exception:
        return
