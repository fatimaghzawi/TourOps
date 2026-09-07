from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.supplier_reservations.constants import SERVICE_TYPE_LABELS
from apps.supplier_reservations.emails import EMAIL_TYPES, SupplierEmailService
from apps.supplier_reservations.forms import (
    ConfirmReservationForm,
    SupplierEmailForm,
    SupplierReservationForm,
)
from apps.supplier_reservations.services import SupplierReservationService
from apps.tours.services import TourService
from core.access import OPERATIONS_ROLES
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


def _unavailable(request):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect("supplier_reservations:list")


def _choices():
    service = SupplierReservationService()
    tours = [(row["id"], f"{row['name']} · {row['code']}") for row in TourService().list_presented()]
    docs = service.repository.list_suppliers()
    suppliers = [
        (str(doc["_id"]), doc.get("name") or doc.get("supplier_number") or "Supplier") for doc in docs
    ]
    types = {str(doc["_id"]): doc.get("supplier_type") or "" for doc in docs}
    return tours, suppliers, types


def _tour_dates(tour_id):
    if not tour_id:
        return {}
    try:
        tour = TourService().get_presented(tour_id, include_extras=False)
    except TourOpsError:
        return {}
    initial = {"tour_id": tour_id}
    start = tour.get("start_date")
    end = tour.get("end_date")
    if hasattr(start, "date"):
        initial["start_date"] = start.date()
    elif isinstance(start, date):
        initial["start_date"] = start
    if hasattr(end, "date"):
        initial["end_date"] = end.date()
    elif isinstance(end, date):
        initial["end_date"] = end
    return initial


@login_required
@role_required(*OPERATIONS_ROLES)
def reservation_list(request):
    service = SupplierReservationService()
    filters = {
        "tour_id": (request.GET.get("tour_id") or "").strip() or None,
        "supplier_id": (request.GET.get("supplier_id") or "").strip() or None,
        "status": (request.GET.get("status") or "").strip() or None,
    }
    service_type = (request.GET.get("type") or "").strip().upper()
    try:
        desk = service.ops_desk()
        reservations = service.list_presented()
        tours, suppliers, _types = _choices()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Supplier reservations are unavailable.")
        desk, reservations, tours, suppliers = {"requested": 0, "confirmed": 0, "upcoming": 0, "release_watch": [], "awaiting": []}, [], [], []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        desk, reservations, tours, suppliers = {"requested": 0, "confirmed": 0, "upcoming": 0, "release_watch": [], "awaiting": []}, [], [], []
    return render(
        request,
        "supplier_reservations/list.html",
        {
            "page_title": "Supplier reservations",
            "page_heading": "Supplier reservations",
            "reservations": reservations,
            "desk": desk,
            "filters": {
                "tour_id": filters["tour_id"] or "",
                "supplier_id": filters["supplier_id"] or "",
                "status": filters["status"] or "",
                "type": service_type,
            },
            "tours": tours,
            "suppliers": suppliers,
            "service_types": SERVICE_TYPE_LABELS,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def reservation_create(request):
    try:
        tours, suppliers, _types = _choices()
    except DatabaseUnavailableError:
        return _unavailable(request)
    tour_id = (request.POST.get("tour_id") or request.GET.get("tour_id") or "").strip()
    supplier_id = (request.POST.get("supplier_id") or request.GET.get("supplier_id") or "").strip()
    initial = _tour_dates(tour_id)
    if supplier_id:
        initial["supplier_id"] = supplier_id
    lock_tour = bool(request.GET.get("tour_id"))
    lock_supplier = bool(request.GET.get("supplier_id"))
    form = SupplierReservationForm(
        request.POST or None,
        tour_choices=tours,
        supplier_choices=suppliers,
        lock_tour=lock_tour,
        lock_supplier=lock_supplier,
        initial=initial or None,
    )
    if request.method == "POST" and form.is_valid():
        payload = dict(form.cleaned_data)
        try:
            reservation = SupplierReservationService().create(
                actor_id=get_session_user(request)["id"],
                **payload,
            )
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Recorded {reservation['reservation_number']}. Contact the supplier externally, then record their confirmation.")
            return redirect("supplier_reservations:detail", id=str(reservation["_id"]))
    return render(
        request,
        "supplier_reservations/form.html",
        {
            "form": form,
            "page_title": "New supplier reservation",
            "page_heading": "Arrange supplier",
            "submit_label": "Save reservation",
            "locked_tour_label": dict(tours).get(tour_id, ""),
            "locked_supplier_label": dict(suppliers).get(supplier_id, ""),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def reservation_edit(request, id):
    service = SupplierReservationService()
    try:
        record = service.get_presented(id)
        tours, suppliers, _types = _choices()
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Supplier reservation not found.")
        return redirect("supplier_reservations:list")
    initial = {
        "tour_id": record["tour_id"],
        "supplier_id": record["supplier_id"],
        "start_date": record["start_date"].date() if hasattr(record.get("start_date"), "date") else record.get("start_date"),
        "end_date": record["end_date"].date() if hasattr(record.get("end_date"), "date") else record.get("end_date"),
        "release_date": record["release_date"].date() if hasattr(record.get("release_date"), "date") else record.get("release_date"),
        "confirmation_number": record.get("confirmation_number") or "",
        "quantity": record.get("quantity") or "",
        "notes": record.get("notes") or "",
        "status": record.get("status"),
    }
    form = SupplierReservationForm(
        request.POST or None,
        tour_choices=tours,
        supplier_choices=suppliers,
        lock_tour=True,
        lock_supplier=True,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        payload = dict(form.cleaned_data)
        payload.pop("tour_id", None)
        payload.pop("supplier_id", None)
        try:
            service.update(id, actor_id=get_session_user(request)["id"], **payload)
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Updated {record['number']}.")
            return redirect("supplier_reservations:detail", id=id)
    return render(
        request,
        "supplier_reservations/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['number']}",
            "page_heading": f"Edit {record['number']}",
            "submit_label": "Save changes",
            "record": record,
            "locked_tour_label": record.get("tour"),
            "locked_supplier_label": record.get("supplier"),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
def reservation_detail(request, id):
    service = SupplierReservationService()
    try:
        record = service.get_presented(id)
        snapshot = service.accommodation_snapshot(record["tour_id"]) if record.get("tour_id") else {}
        expenses = service.related_expenses(supplier_id=record["supplier_id"], tour_id=record["tour_id"])
        activity = []
        from apps.audit.services import AuditService

        activity = AuditService().for_entity("supplier_reservations", id, limit=20)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Supplier reservation not found.")
        return redirect("supplier_reservations:list")
    return render(
        request,
        "supplier_reservations/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Supplier reservations", "url": reverse("supplier_reservations:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "snapshot": snapshot,
            "expenses": expenses,
            "activity": activity,
            "confirm_form": ConfirmReservationForm(),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def reservation_confirm(request, id):
    form = ConfirmReservationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter the supplier confirmation number received outside TourOps.")
        return redirect("supplier_reservations:detail", id=id)
    try:
        SupplierReservationService().confirm(
            id,
            actor_id=get_session_user(request)["id"],
            confirmation_number=form.cleaned_data["confirmation_number"],
            notes=form.cleaned_data.get("notes"),
        )
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("supplier_reservations:detail", id=id)
    messages.success(request, "Supplier confirmation recorded. No expense was created.")
    return redirect("supplier_reservations:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def reservation_cancel(request, id):
    try:
        SupplierReservationService().cancel(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("supplier_reservations:detail", id=id)
    messages.success(request, "Supplier reservation cancelled. Tour seats and finance were not changed.")
    return redirect("supplier_reservations:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def reservation_email(request, id):
    mailer = SupplierEmailService()
    kind = (request.POST.get("kind") or request.GET.get("kind") or "request").strip().lower()
    try:
        generated = mailer.build(id, kind)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("supplier_reservations:detail", id=id)

    form = SupplierEmailForm(
        request.POST or None,
        kind_choices=EMAIL_TYPES,
        initial={"kind": kind, "subject": generated["subject"], "body": generated["body"]},
    )
    if request.method == "POST" and form.is_valid():
        actor = get_session_user(request)["id"]
        cleaned = form.cleaned_data
        if "preview" in request.POST or cleaned["kind"] != kind:
            try:
                generated = mailer.build(id, cleaned["kind"], extra_note=cleaned.get("extra_note") or "")
            except TourOpsError as extra:
                messages.error(request, extra.message)
            else:
                form = SupplierEmailForm(
                    kind_choices=EMAIL_TYPES,
                    initial={
                        "kind": cleaned["kind"],
                        "subject": generated["subject"],
                        "body": generated["body"],
                        "extra_note": cleaned.get("extra_note") or "",
                    },
                )
        elif "copy" in request.POST:
            mailer.mark_generated(actor_id=actor, reservation_id=id, subject=cleaned["subject"])
            messages.success(request, "Email generated. Copy it into your mail client — the supplier does not use TourOps.")
        elif "send" in request.POST:
            result = mailer.send(
                to=generated["to"],
                subject=cleaned["subject"],
                body=cleaned["body"],
                actor_id=actor,
                reservation_id=id,
            )
            if result["sent"]:
                messages.success(request, f"Email sent to {generated['to']}.")
                return redirect("supplier_reservations:detail", id=id)
            mailer.mark_generated(actor_id=actor, reservation_id=id, subject=cleaned["subject"])
            messages.warning(
                request,
                "Email generated successfully. Sending is not configured in this environment. "
                "Copy the message or open your email client.",
            )
            generated["subject"] = cleaned["subject"]
            generated["body"] = cleaned["body"]
        else:
            mailer.mark_generated(actor_id=actor, reservation_id=id, subject=cleaned["subject"])
            generated["subject"] = cleaned["subject"]
            generated["body"] = cleaned["body"]

    mailto = (
        f"mailto:{generated['to']}"
        f"?subject={quote(generated['subject'] or '')}"
        f"&body={quote(generated['body'] or '')}"
    )
    return render(
        request,
        "supplier_reservations/email.html",
        {
            "page_title": "Email supplier",
            "page_heading": "Email supplier",
            "form": form,
            "email": generated,
            "mailto": mailto,
            "record_id": id,
        },
    )

