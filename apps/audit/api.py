from datetime import datetime, timezone

from apps.audit.services import AuditService
from core.exceptions import ValidationError
from core.http import guarded, query_value, resource_id
from core.responses import success_response
from core.utils import utcnow


def _date(value: str | None, *, end: bool = False):
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValidationError("Invalid date. Use YYYY-MM-DD.")
    if end:
        return day.replace(hour=23, minute=59, second=59)
    return day


@guarded
def list_audit_logs(request, **kwargs):
    items = AuditService().list_presented(
        user_id=query_value(request, "user_id"),
        action=query_value(request, "action"),
        entity_type=query_value(request, "entity_type"),
        date_from=_date(query_value(request, "from", "date_from")),
        date_to=_date(query_value(request, "to", "date_to"), end=True),
    )
    return success_response({"audit_logs": items, "generated_at": utcnow().isoformat()})


@guarded
def get_audit_log(request, **kwargs):
    return success_response(AuditService().get_presented(resource_id(kwargs)))
