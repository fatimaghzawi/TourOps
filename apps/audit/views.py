from datetime import datetime, timezone

from django.contrib import messages
from django.shortcuts import render

from apps.accounts.services import UserService
from apps.audit.constants import ACTION_CHOICES, ENTITY_CHOICES
from apps.audit.services import AuditService
from core.access import OWNER_ROLES
from core.exceptions import DatabaseUnavailableError, TourOpsError, ValidationError
from core.permissions import login_required, role_required


def _parse_day(value: str | None, *, end: bool = False):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as extra:
        raise ValidationError("Invalid date. Use YYYY-MM-DD.") from extra
    if end:
        return day.replace(hour=23, minute=59, second=59)
    return day


@login_required
@role_required(*OWNER_ROLES)
def audit_list(request):
    user_id = (request.GET.get("user_id") or "").strip()
    action = (request.GET.get("action") or "").strip().upper()
    entity_type = (request.GET.get("entity_type") or "").strip()
    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    try:
        logs = AuditService().list_presented(
            user_id=user_id or None,
            action=action or None,
            entity_type=entity_type or None,
            date_from=_parse_day(date_from),
            date_to=_parse_day(date_to, end=True),
        )
        users = UserService().list_users()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Audit logs are unavailable.")
        logs, users = [], []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        logs, users = [], []
    return render(
        request,
        "audit/list.html",
        {
            "page_title": "Audit logs",
            "page_heading": "Activity timeline",
            "logs": logs,
            "users": users,
            "action_choices": ACTION_CHOICES,
            "entity_choices": ENTITY_CHOICES,
            "filters": {
                "user_id": user_id,
                "action": action,
                "entity_type": entity_type,
                "from": date_from,
                "to": date_to,
            },
        },
    )
