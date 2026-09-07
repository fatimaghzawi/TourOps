from collections import OrderedDict

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django import forms

from apps.attachments.constants import IMAGE_CONTENT_TYPES, MAX_GALLERY_FILES
from apps.attachments.services import AttachmentService
from apps.packages.services import PackageService
from apps.supplier_reservations.constants import SERVICE_TYPE_LABELS
from apps.supplier_reservations.services import SupplierReservationService
from apps.suppliers.offerings import SupplierOfferingService
from apps.tours.forms import TourForm, initial_from_package, initial_from_tour
from apps.tours.services import TourService
from core.access import OPERATIONS_ROLES
from core.constants import AttachmentCategory, AttachmentEntityType
from core.exceptions import DatabaseUnavailableError, NotFoundError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


def _unavailable(request, next_name="tours:list"):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect(next_name)


def _form_payload(form: TourForm, post=None) -> dict:
    data = form.cleaned_data
    payload = {
        "name": data.get("name"),
        "package_id": data.get("package_id") or None,
        "city": data.get("city"),
        "country": data.get("country"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "capacity": data.get("capacity"),
        "selling_price_per_person": data.get("selling_price_per_person"),
        "currency": data.get("currency"),
        "included_services": data.get("included_services"),
        "excluded_services": data.get("excluded_services"),
        "description": data.get("description"),
    }
    if data.get("status"):
        payload["status"] = data["status"]
    if post and post.get("override_services") == "1":
        payload["service_ids"] = post.getlist("service_ids")
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _package_choices():
    return PackageService().list_options()


def _reservation_groups(rows):
    buckets = OrderedDict((key, []) for key in SERVICE_TYPE_LABELS)
    extra = []
    for row in rows or []:
        if row.get("is_cancelled"):
            continue
        key = row.get("service_type")
        if key in buckets:
            buckets[key].append(row)
        else:
            extra.append(row)
    groups = [
        {"key": key, "label": SERVICE_TYPE_LABELS[key], "rows": items}
        for key, items in buckets.items()
        if items
    ]
    if extra:
        groups.append({"key": "OTHER", "label": "Other", "rows": extra})
    return groups


def _catalog_context(selected_ids=None):
    selected = {str(item) for item in (selected_ids or []) if item}
    catalog = SupplierOfferingService().list_catalog()
    for row in catalog:
        row["selected"] = row["id"] in selected
    return catalog


def _attach_galleries(tours: list[dict]) -> list[dict]:
    grouped = AttachmentService().gallery_for_tours([row.get("id") for row in tours])
    for tour in tours:
        photos = grouped.get(tour.get("id"), [])
        tour["gallery"] = photos
        tour["cover"] = photos[0] if photos else None
    return tours


def _gallery_room(tour_id=None) -> int:
    if not tour_id:
        return MAX_GALLERY_FILES
    existing = AttachmentService().gallery_for_tours([str(tour_id)]).get(str(tour_id), [])
    return max(MAX_GALLERY_FILES - len(existing), 0)


def _save_gallery(request, tour_id) -> int:
    uploads = list(request.FILES.getlist("gallery") or [])
    if not uploads:
        return 0
    existing = AttachmentService().gallery_for_tours([str(tour_id)]).get(str(tour_id), [])
    room = max(MAX_GALLERY_FILES - len(existing), 0)
    if room <= 0:
        messages.error(request, f"This tour already has {MAX_GALLERY_FILES} gallery photos.")
        return 0
    extra = uploads[room:]
    uploads = uploads[:room]
    if extra:
        messages.error(request, f"Only {MAX_GALLERY_FILES} gallery photos are kept. Extra files were skipped.")
    saved = 0
    actor_id = get_session_user(request)["id"]
    for upload in uploads:
        content_type = (getattr(upload, "content_type", "") or "").lower()
        if content_type not in IMAGE_CONTENT_TYPES:
            messages.error(request, f"{getattr(upload, 'name', 'File')} is not a JPG, PNG, WebP, or GIF.")
            continue
        try:
            AttachmentService().create(
                actor_id=actor_id,
                actor_role=get_session_user(request)["role"],
                entity_type=AttachmentEntityType.TOURS.value,
                entity_id=tour_id,
                category=AttachmentCategory.GALLERY.value,
                upload=upload,
            )
        except TourOpsError as extra_err:
            messages.error(request, extra_err.message)
        else:
            saved += 1
    return saved


@login_required
@role_required(*OPERATIONS_ROLES)
def tour_list(request):
    try:
        tours = TourService().list_presented()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Tours are unavailable.")
        tours = []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        tours = []
    else:
        try:
            _attach_galleries(tours)
        except TourOpsError:
            pass
    return render(
        request,
        "tours/list.html",
        {
            "page_title": "Tours",
            "page_heading": "Departures",
            "tours": tours,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def tour_create(request):
    try:
        choices = _package_choices()
    except DatabaseUnavailableError:
        return _unavailable(request)
    if not choices:
        return render(
            request,
            "tours/form.html",
            {
                "form": None,
                "page_title": "New tour",
                "page_heading": "New departure",
                "needs_package": True,
            },
        )
    initial = {}
    selected_package = None
    package_id = (request.POST.get("package_id") or request.GET.get("package_id") or "").strip()
    if package_id:
        try:
            selected_package = PackageService().get_presented(package_id, include_extras=True)
            if request.method == "GET":
                initial = initial_from_package(selected_package)
            if selected_package["id"] not in {item[0] for item in choices}:
                choices = [(selected_package["id"], f"{selected_package['name']} (inactive)")] + list(choices)
        except (NotFoundError, TourOpsError):
            messages.error(request, "Package not found.")
            selected_package = None
    form = TourForm(request.POST or None, initial=initial or None, package_choices=choices)
    if request.method == "POST" and form.is_valid():
        try:
            tour = TourService().create(actor_id=get_session_user(request)["id"], **_form_payload(form, request.POST))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            added = _save_gallery(request, tour["_id"])
            if added:
                messages.success(request, f"Created {tour['tour_code']} with {added} gallery photo{'s' if added != 1 else ''}.")
            else:
                messages.success(request, f"Created {tour['tour_code']}.")
            return redirect("tours:detail", id=str(tour["_id"]))
    return render(
        request,
        "tours/form.html",
        {
            "form": form,
            "page_title": "New tour",
            "page_heading": "New departure",
            "submit_label": "Save tour",
            "selected_package": selected_package,
            "catalog": _catalog_context(
                request.POST.getlist("service_ids")
                if request.method == "POST" and request.POST.get("override_services") == "1"
                else [line.get("supplier_service_id") for line in (selected_package or {}).get("services") or []]
            ),
            "override_services": request.POST.get("override_services") == "1" if request.method == "POST" else False,
            "gallery_room": MAX_GALLERY_FILES,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
def tour_detail(request, id):
    tab = (request.GET.get("tab") or "overview").strip().lower()
    allowed = {"overview", "gallery", "bookings", "travelers", "services", "reservations", "expenses", "profit", "activity"}
    if tab not in allowed:
        tab = "overview"
    try:
        record = TourService().get_presented(id)
        record["planned_ops"] = SupplierReservationService().match_planned(
            record.get("services") or [],
            record.get("reservations") or [],
        )
        record["reservation_groups"] = _reservation_groups(record.get("reservations") or [])
        gallery = AttachmentService().gallery_for_tours([record["id"]]).get(record["id"], [])
        record["gallery"] = gallery
        record["cover"] = gallery[0] if gallery else None
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Tour not found.")
        return redirect("tours:list")
    return render(
        request,
        "tours/detail.html",
        {
            "page_title": record["name"],
            "page_heading": record["name"],
            "crumbs": [
                {"label": "Tours", "url": reverse("tours:list")},
                {"label": record["code"], "url": ""},
            ],
            "record": record,
            "tab": tab,
            "gallery_room": _gallery_room(record["id"]),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def tour_edit(request, id):
    service = TourService()
    try:
        record = service.get_presented(id, include_extras=True)
        choices = _package_choices()
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Tour not found.")
        return redirect("tours:list")
    form = TourForm(
        request.POST or None,
        initial=initial_from_tour(record),
        package_choices=choices + [(record.get("package_id") or "", record.get("package") or "Package")],
        include_status=True,
    )
    form.fields["package_id"].widget = forms.HiddenInput()
    if request.method == "POST" and form.is_valid():
        payload = _form_payload(form, request.POST)
        payload.pop("package_id", None)
        try:
            service.update(id, actor_id=get_session_user(request)["id"], **payload)
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            added = _save_gallery(request, id)
            if added:
                messages.success(request, f"Updated {record['code']} and added {added} gallery photo{'s' if added != 1 else ''}.")
            else:
                messages.success(request, f"Updated {record['code']}.")
            return redirect("tours:detail", id=id)
    return render(
        request,
        "tours/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['name']}",
            "page_heading": f"Edit {record['name']}",
            "submit_label": "Save changes",
            "record": record,
            "package_locked": True,
            "catalog": _catalog_context(
                request.POST.getlist("service_ids")
                if request.method == "POST" and request.POST.get("override_services") == "1"
                else [line.get("supplier_service_id") for line in (record.get("services") or [])]
            ),
            "override_services": request.POST.get("override_services") == "1" if request.method == "POST" else False,
            "gallery": AttachmentService().gallery_for_tours([id]).get(id, []),
            "gallery_room": _gallery_room(id),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def tour_gallery_add(request, id):
    try:
        TourService().get_presented(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Tour not found.")
        return redirect("tours:list")
    added = _save_gallery(request, id)
    if added:
        messages.success(
            request,
            f"Added {added} gallery photo{'s' if added != 1 else ''}.",
        )
    return redirect(f"{reverse('tours:detail', args=[id])}?tab=gallery")


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def tour_delete(request, id):
    try:
        TourService().soft_delete(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("tours:detail", id=id)
    messages.success(request, "Tour deleted.")
    return redirect("tours:list")


@login_required
@role_required(*OPERATIONS_ROLES)
def availability(request):
    try:
        tours = TourService().availability()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Availability is unavailable.")
        tours = []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        tours = []
    return render(
        request,
        "tours/availability.html",
        {
            "page_title": "Availability",
            "page_heading": "Seat availability",
            "tours": tours,
        },
    )
