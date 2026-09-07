from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.supplier_payments.services import SupplierPaymentService
from apps.supplier_reservations.services import SupplierReservationService
from apps.suppliers.forms import SupplierForm, initial_from_record
from apps.suppliers.offering_forms import SupplierOfferingForm
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from core.access import ALL_ROLES, OPERATIONS_ROLES
from core.constants import PaymentMethod, RecordStatus, SupplierType
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


_INFO_KEYS = (
    "star_rating",
    "vehicle_type",
    "fleet_size",
    "seats_per_vehicle",
    "license_number",
    "coverage_areas",
    "languages",
    "years_experience",
    "specialties",
    "iata_code",
    "alliance",
    "activity_kinds",
    "typical_duration_hours",
    "location",
    "cuisine",
    "seating_capacity",
    "meal_types",
    "policy_types",
    "coverage_notes",
    "details",
)


def _unavailable(request, next_name="suppliers:list"):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect(next_name)


def _form_payload(form: SupplierForm) -> dict:
    data = form.cleaned_data
    payload = {
        "name": data["name"],
        "supplier_type": data["supplier_type"],
        "contact_person": data.get("contact_person"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "country": data.get("country"),
        "city": data.get("city"),
        "street": data.get("street"),
        "tax_number": data.get("tax_number"),
        "payment_terms": data.get("payment_terms"),
        "preferred_payment_method": data.get("preferred_payment_method") or None,
        "notes": data.get("notes"),
    }
    if data.get("preferred_payment_method") == PaymentMethod.BANK_TRANSFER.value:
        payload.update(
            {
                "bank_name": data.get("bank_name"),
                "account_name": data.get("account_name"),
                "iban": data.get("iban"),
                "swift_bic": data.get("swift_bic"),
                "account_number": data.get("account_number"),
            }
        )
    for key in _INFO_KEYS:
        if key in data:
            payload[key] = data[key]
    if data.get("supplier_type") == SupplierType.TOUR_GUIDE.value:
        payload["license_number"] = data.get("guide_license_number")
    if "status" in data and data.get("status"):
        payload["status"] = data["status"]
    return payload


def _directory(request, title, heading, *, supplier_type=None, group=None, type_filter=None):
    service = SupplierService()
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().upper()
    type_query = (request.GET.get("type") or "").strip().upper() or None
    chip_type = type_query or type_filter or supplier_type
    effective_type = supplier_type or (None if group else (type_query or type_filter))
    try:
        suppliers = service.list_presented(
            supplier_type=effective_type,
            group=group,
        )
        reservations = SupplierReservationService().list_presented()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Suppliers are unavailable.")
        suppliers, reservations = [], []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        suppliers, reservations = [], []
    open_by_supplier = {}
    tours_by_supplier = {}
    for row in reservations:
        if row.get("is_cancelled"):
            continue
        key = row.get("supplier_id")
        open_by_supplier[key] = open_by_supplier.get(key, 0) + 1
        tours_by_supplier.setdefault(key, set()).add(row.get("tour_id"))
    for row in suppliers:
        row["open_reservations"] = open_by_supplier.get(row["id"], 0)
        row["tour_count"] = len(tours_by_supplier.get(row["id"], set())) or len(row.get("tours") or [])
    all_for_stats = suppliers if (effective_type or group) else None
    try:
        universe = service.list_presented() if all_for_stats is not None else suppliers
    except (DatabaseUnavailableError, TourOpsError):
        universe = suppliers
    stats = {
        "total": len(universe),
        "active": sum(1 for row in universe if row.get("status") == RecordStatus.ACTIVE.value),
        "hotels": sum(1 for row in universe if row.get("type") == SupplierType.HOTEL.value),
        "transport": sum(1 for row in universe if row.get("type") == SupplierType.TRANSPORTATION.value),
        "guides": sum(1 for row in universe if row.get("type") == SupplierType.TOUR_GUIDE.value),
        "owed": sum((row.get("owed") or 0) for row in universe),
    }
    return render(
        request,
        "suppliers/list.html",
        {
            "page_title": title,
            "page_heading": heading,
            "suppliers": suppliers,
            "type_filter": chip_type,
            "q": query,
            "status_filter": status,
            "stats": stats,
        },
    )


@login_required
@role_required(*ALL_ROLES)
def supplier_list(request):
    type_filter = (request.GET.get("type") or "").strip().upper() or None
    return _directory(request, "Suppliers", "Suppliers", supplier_type=type_filter, type_filter=type_filter)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            supplier = SupplierService().create(actor_id=get_session_user(request)["id"], **_form_payload(form))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Created {supplier['supplier_number']}. Add the services this supplier provides.")
            return redirect(f"{reverse('suppliers:detail', kwargs={'id': str(supplier['_id'])})}?tab=services")
    return render(
        request,
        "suppliers/form.html",
        {
            "form": form,
            "page_title": "New supplier",
            "page_heading": "New supplier",
            "submit_label": "Save supplier",
        },
    )


@login_required
@role_required(*ALL_ROLES)
def hotels(request):
    return _directory(request, "Hotels", "Hotels", supplier_type="HOTEL", type_filter="HOTEL")


@login_required
@role_required(*ALL_ROLES)
def transportation(request):
    return _directory(request, "Transportation", "Transportation", supplier_type="TRANSPORTATION", type_filter="TRANSPORTATION")


@login_required
@role_required(*ALL_ROLES)
def tour_guides(request):
    return _directory(request, "Tour guides", "Tour guides", supplier_type="TOUR_GUIDE", type_filter="TOUR_GUIDE")


@login_required
@role_required(*ALL_ROLES)
def other_suppliers(request):
    return _directory(request, "Other suppliers", "Other suppliers", group="OTHER", type_filter="OTHER")


@login_required
@role_required(*OPERATIONS_ROLES)
def catalog_index(request):
    supplier_id = (request.GET.get("supplier_id") or "").strip()
    if supplier_id:
        return redirect("suppliers:service_create", id=supplier_id)
    try:
        catalog = SupplierOfferingService().list_catalog()
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        catalog = []
    return render(
        request,
        "suppliers/catalog.html",
        {
            "page_title": "Supplier services",
            "page_heading": "Supplier services",
            "catalog": catalog,
        },
    )


@login_required
@role_required(*ALL_ROLES)
def supplier_detail(request, id):
    tab = (request.GET.get("tab") or "overview").strip().lower()
    if tab not in {"overview", "services", "tours", "reservations", "expenses", "payments", "activity"}:
        tab = "overview"
    try:
        record = SupplierService().get_presented(id)
        record["offerings"] = SupplierOfferingService().list_for_supplier(id)
        reservations = SupplierReservationService().list_presented(supplier_id=id)
        payments = []
        activity = []
        try:
            from apps.audit.services import AuditService

            activity = AuditService().for_entity("suppliers", id, limit=20)
        except Exception:
            activity = []
        try:
            payments = SupplierPaymentService().list_for_supplier(id)
        except Exception:
            payments = []
        record["reservations"] = reservations
        record["payments"] = payments
        record["activity"] = activity
        record["open_reservation_count"] = sum(1 for row in reservations if not row.get("is_cancelled"))
        record["upcoming_reservations"] = [row for row in reservations if row.get("is_upcoming")]
        record["confirmed_reservations"] = [row for row in reservations if row.get("is_confirmed")]
        record["open_bill_count"] = len(record.get("open_expenses") or [])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Supplier not found.")
        return redirect("suppliers:list")
    return render(
        request,
        "suppliers/detail.html",
        {
            "page_title": record["name"],
            "page_heading": record["name"],
            "crumbs": [
                {"label": "Suppliers", "url": reverse("suppliers:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "tab": tab,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def supplier_edit(request, id):
    service = SupplierService()
    try:
        record = service.get_presented(id, include_extras=False)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Supplier not found.")
        return redirect("suppliers:list")

    form = SupplierForm(request.POST or None, initial=initial_from_record(record), include_status=True)
    if request.method == "POST" and form.is_valid():
        try:
            service.update(id, actor_id=get_session_user(request)["id"], **_form_payload(form))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Updated {record['number']}.")
            return redirect("suppliers:detail", id=id)
    return render(
        request,
        "suppliers/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['name']}",
            "page_heading": f"Edit {record['name']}",
            "submit_label": "Save changes",
            "record": record,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def supplier_delete(request, id):
    try:
        SupplierService().soft_delete(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("suppliers:detail", id=id)
    messages.success(request, "Supplier deleted.")
    return redirect("suppliers:list")


def _offering_payload(form: SupplierOfferingForm) -> dict:
    data = form.cleaned_data
    payload = {
        "name": data["name"],
        "service_kind": data["service_kind"],
        "estimated_cost": data.get("estimated_cost"),
        "cost_basis": data.get("cost_basis"),
        "currency": data.get("currency"),
        "description": data.get("description"),
    }
    if data.get("status"):
        payload["status"] = data["status"]
    return payload


def _active_suppliers():
    return SupplierService().list_presented(status=RecordStatus.ACTIVE.value)


def _supplier_choices(rows=None):
    rows = _active_suppliers() if rows is None else rows
    return [
        (row["id"], f"{row.get('name') or 'Supplier'} · {row.get('type_label') or row.get('type') or ''}".strip(" ·"))
        for row in rows
    ]


def _picker_suppliers(rows, *, default_kind_by_type):
    picker = []
    for row in rows:
        search = " ".join(
            part
            for part in (
                row.get("name"),
                row.get("type_label"),
                row.get("number"),
                row.get("city"),
                row.get("country"),
                row.get("contact"),
            )
            if part
        )
        picker.append(
            {
                "id": row["id"],
                "name": row.get("name") or "Supplier",
                "type_label": row.get("type_label") or "",
                "number": row.get("number") or "",
                "city": row.get("city") or "",
                "default_kind": default_kind_by_type.get(row.get("type"), "OTHER"),
                "search": search,
            }
        )
    return picker


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def offering_create(request, id=None):
    from apps.suppliers.constants import DEFAULT_KIND_BY_SUPPLIER

    try:
        suppliers = _active_suppliers()
        choices = _supplier_choices(suppliers)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        suppliers = []
        choices = []

    selected = (id or request.POST.get("supplier_id") or request.GET.get("supplier_id") or "").strip()
    supplier = None
    if selected:
        try:
            supplier = SupplierService().get_presented(selected, include_extras=False)
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError:
            if id:
                messages.error(request, "Supplier not found.")
                return redirect("suppliers:list")
            messages.error(request, "Select an existing supplier.")
            supplier = None
            selected = ""

    if not id and not choices:
        return render(
            request,
            "suppliers/service_form.html",
            {
                "form": None,
                "page_title": "Add service",
                "page_heading": "Add supplier service",
                "needs_supplier": True,
            },
        )

    initial = {}
    if supplier:
        initial["supplier_id"] = supplier["id"]
        initial["service_kind"] = DEFAULT_KIND_BY_SUPPLIER.get(supplier.get("type"), "OTHER")
    form = SupplierOfferingForm(
        request.POST or None,
        initial=initial or None,
        supplier_choices=None if id else choices,
    )
    if request.method == "POST" and form.is_valid():
        supplier_id = id or form.cleaned_data.get("supplier_id")
        try:
            offering = SupplierOfferingService().create(
                actor_id=get_session_user(request)["id"],
                supplier_id=supplier_id,
                **_offering_payload(form),
            )
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Added {offering['name']}.")
            return redirect(f"{reverse('suppliers:detail', kwargs={'id': str(supplier_id)})}?tab=services")
    return render(
        request,
        "suppliers/service_form.html",
        {
            "form": form,
            "page_title": f"Add service · {supplier['name']}" if supplier else "Add service",
            "page_heading": "Add supplier service",
            "submit_label": "Save service",
            "supplier": supplier,
            "pick_supplier": not id,
            "picker_suppliers": [] if id else _picker_suppliers(suppliers, default_kind_by_type=DEFAULT_KIND_BY_SUPPLIER),
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def offering_edit(request, id, service_id):
    try:
        supplier = SupplierService().get_presented(id, include_extras=False)
        offering = SupplierOfferingService().get_presented(service_id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Service not found.")
        return redirect("suppliers:detail", id=id)
    if offering["supplier_id"] != str(id):
        messages.error(request, "That service does not belong to this supplier.")
        return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
    form = SupplierOfferingForm(
        request.POST or None,
        initial={
            "name": offering["name"],
            "service_kind": offering["service_kind"],
            "estimated_cost": offering["estimated_cost"],
            "cost_basis": offering.get("cost_basis"),
            "currency": offering["currency"],
            "description": offering["description"],
            "status": offering["status"],
        },
        include_status=True,
    )
    if request.method == "POST" and form.is_valid():
        try:
            SupplierOfferingService().update(
                service_id,
                actor_id=get_session_user(request)["id"],
                **_offering_payload(form),
            )
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Updated {offering['name']}.")
            return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
    return render(
        request,
        "suppliers/service_form.html",
        {
            "form": form,
            "page_title": f"Edit {offering['name']}",
            "page_heading": f"Edit {offering['name']}",
            "submit_label": "Save changes",
            "supplier": supplier,
            "offering": offering,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def offering_delete(request, id, service_id):
    try:
        SupplierOfferingService().soft_delete(service_id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
    messages.success(request, "Service deleted.")
    return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def offering_set_status(request, id, service_id):
    status = (request.POST.get("status") or "").strip().upper()
    if status not in {RecordStatus.ACTIVE.value, RecordStatus.INACTIVE.value}:
        messages.error(request, "Invalid service status.")
        return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
    try:
        offering = SupplierOfferingService().get_presented(service_id)
        if offering["supplier_id"] != str(id):
            messages.error(request, "That service does not belong to this supplier.")
            return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
        SupplierOfferingService().set_status(service_id, status, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
    messages.success(request, "Service deactivated." if status == RecordStatus.INACTIVE.value else "Service activated.")
    return redirect(f"{reverse('suppliers:detail', kwargs={'id': id})}?tab=services")
