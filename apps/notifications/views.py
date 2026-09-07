from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.notifications.constants import TYPE_CHOICES
from apps.notifications.services import NotificationService
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required


def _target_url(item: dict) -> str:
    kind = item.get("type") or item.get("kind")
    entity_type = item.get("related_entity_type")
    entity_id = item.get("related_entity_id")
    if entity_type == "expenses" and entity_id:
        return reverse("expenses:detail", args=[entity_id])
    if entity_type == "supplier_payments" and entity_id:
        return reverse("supplier_payments:detail", args=[entity_id])
    if entity_type == "bookings" and entity_id:
        return reverse("bookings:detail", args=[entity_id])
    if entity_type == "tours" and entity_id:
        return reverse("tours:detail", args=[entity_id])
    if entity_type == "supplier_reservations" and entity_id:
        return reverse("supplier_reservations:detail", args=[entity_id])
    if entity_type == "invoices":
        return reverse("invoices:list")
    if entity_type == "payments":
        return reverse("payments:list")
    if entity_type == "refunds":
        return reverse("refunds:list")
    if entity_type == "attachments":
        return reverse("attachments:list")
    if kind == "refund":
        return reverse("refunds:list")
    if kind == "payment":
        return reverse("payments:list")
    if kind == "supplier":
        return reverse("supplier_payments:list")
    if kind == "expense":
        return reverse("expenses:list")
    if kind == "booking":
        return reverse("bookings:list")
    if kind == "tour":
        return reverse("tours:list")
    return reverse("notifications:list")


@login_required
def notification_list(request):
    user = get_session_user(request)
    unread_only = request.GET.get("unread") in {"1", "true", "yes"}
    kind = (request.GET.get("type") or "").strip().lower()
    try:
        items = NotificationService().list_for_user(
            user["id"],
            unread_only=unread_only,
            notification_type=kind or None,
        )
        unread_count = NotificationService().unread_count(user["id"])
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Notifications are unavailable.")
        items, unread_count = [], 0
    except TourOpsError as extra:
        messages.error(request, extra.message)
        items, unread_count = [], 0
    for item in items:
        item["href"] = _target_url(item)
    return render(
        request,
        "notifications/list.html",
        {
            "page_title": "Notifications",
            "page_heading": "Notification center",
            "notifications": items,
            "unread_count_page": unread_count,
            "type_choices": TYPE_CHOICES,
            "filters": {"unread": unread_only, "type": kind},
        },
    )


@login_required
def notification_open(request, id):
    user = get_session_user(request)
    try:
        item = NotificationService().mark_read(id, user["id"])
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB.")
        return redirect("notifications:list")
    except TourOpsError:
        return redirect("notifications:list")
    return redirect(_target_url(item))


@login_required
@require_POST
def notification_mark_read(request, id):
    try:
        NotificationService().mark_read(id, get_session_user(request)["id"])
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB.")
    except TourOpsError as extra:
        messages.error(request, extra.message)
    return redirect(request.POST.get("next") or "notifications:list")


@login_required
@require_POST
def notification_mark_all_read(request):
    try:
        result = NotificationService().mark_all_read(get_session_user(request)["id"])
        messages.success(request, f"Marked {result['updated']} notification(s) as read.")
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB.")
    except TourOpsError as extra:
        messages.error(request, extra.message)
    return redirect("notifications:list")
