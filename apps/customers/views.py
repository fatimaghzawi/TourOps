from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.attachments.forms import AttachmentUploadForm
from apps.attachments.services import AttachmentService
from apps.bookings.services import BookingService
from apps.customers.forms import CustomerForm
from apps.customers.services import CustomerService
from apps.invoices.services import InvoiceService
from core.access import ALL_ROLES, OPERATIONS_ROLES, can_access_operations
from core.constants import AttachmentEntityType, InvoiceStatus
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.money import ZERO, to_decimal
from core.permissions import get_session_user, login_required, role_required


def _unavailable(request):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect("customers:list")


def _form_initial(record: dict) -> dict:
    return {
        "first_name": record.get("first_name") or "",
        "last_name": record.get("last_name") or "",
        "email": record.get("email") or "",
        "phone": record.get("phone") or "",
        "city": record.get("city") or "",
        "country": record.get("country") or "",
        "passport": record.get("passport") or "",
        "nationality": record.get("nationality") or "",
        "notes": record.get("notes") or "",
    }


@login_required
@role_required(*OPERATIONS_ROLES)
def customer_list(request):
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().upper()
    try:
        customers = CustomerService().list_presented(query=query or None, status=status or None)
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Customers are unavailable.")
        customers = []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        customers = []
    return render(
        request,
        "customers/list.html",
        {
            "page_title": "Customers",
            "page_heading": "Customers",
            "customers": customers,
            "q": query,
            "status_filter": status,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            customer = CustomerService().create(
                actor_id=get_session_user(request)["id"],
                **form.cleaned_data,
            )
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Created {customer['customer_number']}.")
            return redirect("customers:detail", id=str(customer["_id"]))
    return render(
        request,
        "customers/form.html",
        {
            "form": form,
            "page_title": "New customer",
            "page_heading": "New customer",
            "submit_label": "Save customer",
        },
    )


@login_required
@role_required(*ALL_ROLES)
def customer_detail(request, id):
    try:
        record = CustomerService().get_presented(id)
        bookings = BookingService().list_presented(customer_id=id)
        attachments = AttachmentService().list_for_entity(AttachmentEntityType.CUSTOMERS.value, id)
        invoices = []
        outstanding = ZERO
        for invoice in InvoiceService().list_items(customer_id=id):
            remaining = to_decimal(invoice.get("remaining_amount") or 0)
            live = invoice.get("status") != InvoiceStatus.CANCELLED.value
            can_collect = live and remaining > ZERO
            invoices.append({**invoice, "remaining": remaining, "can_collect": can_collect})
            if can_collect:
                outstanding += remaining
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
        if can_access_operations(request):
            return redirect("customers:list")
        return redirect("finance:customer_balances")
    except TourOpsError:
        messages.error(request, "Customer not found.")
        if can_access_operations(request):
            return redirect("customers:list")
        return redirect("finance:customer_balances")
    upload_form = AttachmentUploadForm(
        initial={"entity_type": AttachmentEntityType.CUSTOMERS.value, "entity_id": id},
        hide_entity=True,
    )
    crumbs = []
    if can_access_operations(request):
        crumbs.append({"label": "Customers", "url": reverse("customers:list")})
    else:
        crumbs.append({"label": "Customer balances", "url": reverse("finance:customer_balances")})
    crumbs.append({"label": record["number"], "url": ""})
    return render(
        request,
        "customers/detail.html",
        {
            "page_title": record["name"],
            "page_heading": record["name"],
            "crumbs": crumbs,
            "record": record,
            "bookings": bookings,
            "invoices": invoices,
            "outstanding": outstanding,
            "attachments": attachments,
            "upload_form": upload_form,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def customer_edit(request, id):
    try:
        record = CustomerService().get_presented(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Customer not found.")
        return redirect("customers:list")
    form = CustomerForm(request.POST or None, initial=_form_initial(record))
    if request.method == "POST" and form.is_valid():
        try:
            CustomerService().update(id, actor_id=get_session_user(request)["id"], **form.cleaned_data)
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Updated {record['number']}.")
            return redirect("customers:detail", id=id)
    return render(
        request,
        "customers/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['name']}",
            "page_heading": f"Edit {record['name']}",
            "submit_label": "Save changes",
            "record": record,
        },
    )
