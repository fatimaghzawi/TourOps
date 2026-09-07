from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.packages.forms import PackageForm, initial_from_package
from apps.packages.services import PackageService
from apps.suppliers.offerings import SupplierOfferingService
from core.access import OPERATIONS_ROLES
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


def _unavailable(request, next_name="packages:list"):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect(next_name)


def _form_payload(form: PackageForm, post=None) -> dict:
    data = form.cleaned_data
    payload = {
        "name": data["name"],
        "city": data.get("city"),
        "country": data.get("country"),
        "duration_days": data["duration_days"],
        "selling_price_per_person": data["selling_price_per_person"],
        "target_margin_percent": data.get("target_margin_percent"),
        "currency": data.get("currency"),
        "default_capacity": data["default_capacity"],
        "included_services": data.get("included_services"),
        "excluded_services": data.get("excluded_services"),
        "description": data.get("description"),
        "services": [{"supplier_service_id": item} for item in (post.getlist("service_ids") if post else [])],
    }
    if data.get("status"):
        payload["status"] = data["status"]
    return payload


def _catalog_context(selected_ids=None):
    selected = {str(item) for item in (selected_ids or []) if item}
    catalog = SupplierOfferingService().list_catalog()
    seen = {row["id"] for row in catalog}
    for service_id in selected:
        if service_id in seen:
            continue
        try:
            row = SupplierOfferingService().get_presented(service_id)
        except TourOpsError:
            continue
        row["unavailable"] = True
        catalog.append(row)
        seen.add(service_id)
    for row in catalog:
        row["selected"] = row["id"] in selected
    return catalog


@login_required
@role_required(*OPERATIONS_ROLES)
def package_list(request):
    try:
        packages = PackageService().list_presented()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Packages are unavailable.")
        packages = []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        packages = []
    return render(
        request,
        "packages/list.html",
        {
            "page_title": "Packages",
            "page_heading": "Travel packages",
            "packages": packages,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def package_create(request):
    form = PackageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            package = PackageService().create(actor_id=get_session_user(request)["id"], **_form_payload(form, request.POST))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Created {package['package_code']}.")
            return redirect("packages:detail", id=str(package["_id"]))
    return render(
        request,
        "packages/form.html",
        {
            "form": form,
            "page_title": "New package",
            "page_heading": "New package",
            "submit_label": "Save package",
            "catalog": _catalog_context(request.POST.getlist("service_ids") if request.method == "POST" else []),
            "has_departures": False,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
def package_detail(request, id):
    try:
        record = PackageService().get_presented(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Package not found.")
        return redirect("packages:list")
    return render(
        request,
        "packages/detail.html",
        {
            "page_title": record["name"],
            "page_heading": record["name"],
            "crumbs": [
                {"label": "Packages", "url": reverse("packages:list")},
                {"label": record["code"], "url": ""},
            ],
            "record": record,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def package_edit(request, id):
    service = PackageService()
    try:
        record = service.get_presented(id, include_extras=True)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Package not found.")
        return redirect("packages:list")
    form = PackageForm(request.POST or None, initial=initial_from_package(record), include_status=True)
    if request.method == "POST" and form.is_valid():
        try:
            service.update(id, actor_id=get_session_user(request)["id"], **_form_payload(form, request.POST))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Updated {record['code']}.")
            return redirect("packages:detail", id=id)
    return render(
        request,
        "packages/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['name']}",
            "page_heading": f"Edit {record['name']}",
            "submit_label": "Save changes",
            "record": record,
            "has_departures": bool(record.get("tours")),
            "catalog": _catalog_context(
                request.POST.getlist("service_ids")
                if request.method == "POST"
                else [line.get("supplier_service_id") for line in record.get("services") or []]
            ),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def package_delete(request, id):
    try:
        PackageService().soft_delete(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("packages:detail", id=id)
    messages.success(request, "Package deleted.")
    return redirect("packages:list")
