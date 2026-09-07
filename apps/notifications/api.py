from apps.notifications.services import NotificationService
from core.http import actor_id, guarded, query_value, resource_id
from core.responses import success_response


@guarded
def list_notifications(request, **kwargs):
    unread = query_value(request, "unread")
    items = NotificationService().list_for_user(
        actor_id(request),
        unread_only=str(unread).lower() in {"1", "true", "yes"} if unread else False,
        notification_type=query_value(request, "type"),
    )
    return success_response(
        {
            "notifications": items,
            "unread_count": NotificationService().unread_count(actor_id(request)),
        }
    )


@guarded
def get_notification(request, **kwargs):
    return success_response(NotificationService().get_for_user(resource_id(kwargs), actor_id(request)))


@guarded
def mark_read(request, **kwargs):
    return success_response(NotificationService().mark_read(resource_id(kwargs), actor_id(request)))


@guarded
def mark_all_read(request, **kwargs):
    return success_response(NotificationService().mark_all_read(actor_id(request)))
