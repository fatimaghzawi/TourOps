from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.attachments.forms import AttachmentUploadForm
from apps.attachments.services import AttachmentService
from apps.expenses.constants import CATEGORY_CHOICES, SCOPE_CHOICES, STATUS_CHOICES
from apps.expenses.forms import ExpenseForm
from apps.expenses.services import ExpenseService
from core.access import FINANCE_ROLES
from core.constants import AttachmentCategory, AttachmentEntityType, DEFAULT_CURRENCY
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


def _options(service: ExpenseService):
    return {
        "supplier_choices": service.list_supplier_options(),
        "tour_choices": service.list_tour_options(),
    }


def _form_payload(form: ExpenseForm) -> dict:
    return {
        "expense_scope": form.cleaned_data["expense_scope"],
        "category": form.cleaned_data["category"],
        "amount": form.cleaned_data["amount"],
        "description": form.cleaned_data["description"],
        "expense_date": form.cleaned_data["expense_date"],
        "currency": form.cleaned_data.get("currency") or DEFAULT_CURRENCY,
        "supplier_id": form.cleaned_data.get("supplier_id") or None,
        "tour_id": form.cleaned_data.get("tour_id") or None,
        "due_date": form.cleaned_data.get("due_date"),
        "receipt_file": form.cleaned_data.get("receipt_file"),
    }


def _unavailable(request, next_name="expenses:list"):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect(next_name)


@login_required
@role_required(*FINANCE_ROLES)
def expense_list(request):
    service = ExpenseService()
    category = (request.GET.get("category") or "").strip().upper()
    status = (request.GET.get("status") or "").strip().upper()
    scope = (request.GET.get("scope") or "").strip().upper()
    overdue = request.GET.get("overdue") in {"1", "true", "yes"}
    try:
        expenses = service.list_presented(
            category=category or None,
            payment_status=status or None,
            expense_scope=scope or None,
            overdue=overdue or None,
        )
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Expenses are unavailable.")
        expenses = []
    except TourOpsError as exc:
        messages.error(request, exc.message)
        expenses = []
        category = status = scope = ""
        overdue = False
    return render(
        request,
        "expenses/list.html",
        {
            "page_title": "Expenses",
            "page_heading": "Expenses",
            "expenses": expenses,
            "category": category,
            "status": status,
            "scope": scope,
            "overdue": overdue,
            "category_choices": CATEGORY_CHOICES,
            "status_choices": STATUS_CHOICES,
            "scope_choices": SCOPE_CHOICES,
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
@require_http_methods(["GET", "POST"])
def expense_create(request):
    service = ExpenseService()
    try:
        options = _options(service)
    except DatabaseUnavailableError:
        return _unavailable(request)
    initial = {}
    if request.method == "GET":
        if request.GET.get("supplier_id"):
            initial["supplier_id"] = request.GET.get("supplier_id")
        if request.GET.get("tour_id"):
            initial["tour_id"] = request.GET.get("tour_id")
            initial["expense_scope"] = "TOUR"
        reservation_id = request.GET.get("reservation_id")
        if reservation_id:
            from apps.supplier_reservations.services import SupplierReservationService

            try:
                reservation = SupplierReservationService().get_presented(reservation_id)
            except TourOpsError:
                reservation = None
            if reservation:
                initial["supplier_id"] = reservation.get("supplier_id") or initial.get("supplier_id")
                initial["tour_id"] = reservation.get("tour_id") or initial.get("tour_id")
                initial["expense_scope"] = "TOUR"
                if reservation.get("is_hotel"):
                    initial["category"] = "HOTEL"
                initial["description"] = (
                    f"Supplier bill for {reservation.get('number')} · "
                    f"{reservation.get('tour')} · {reservation.get('supplier')}"
                )
    form = ExpenseForm(request.POST or None, initial=initial or None, **options)
    if request.method == "POST" and form.is_valid():
        try:
            expense = service.create(actor_id=get_session_user(request)["id"], **_form_payload(form))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f"Created {expense['expense_number']}.")
            return redirect("expenses:detail", id=str(expense["_id"]))
    return render(
        request,
        "expenses/form.html",
        {
            "form": form,
            "page_title": "New expense",
            "page_heading": "Record supplier bill",
            "submit_label": "Save expense",
            "from_reservation": bool(request.GET.get("reservation_id")),
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
def expense_detail(request, id):
    try:
        record = ExpenseService().get_presented(id, include_payments=True)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Expense not found.")
        return redirect("expenses:list")
    try:
        attachments = AttachmentService().list_for_entity(AttachmentEntityType.EXPENSES.value, id)
    except (DatabaseUnavailableError, TourOpsError):
        attachments = []
    upload_form = AttachmentUploadForm(
        initial={
            "entity_type": AttachmentEntityType.EXPENSES.value,
            "entity_id": record["id"],
            "category": AttachmentCategory.RECEIPT.value,
        },
        hide_entity=True,
    )
    return render(
        request,
        "expenses/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Expenses", "url": reverse("expenses:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "attachments": attachments,
            "upload_form": upload_form,
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
@require_http_methods(["GET", "POST"])
def expense_edit(request, id):
    service = ExpenseService()
    try:
        record = service.get_presented(id)
        options = _options(service)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Expense not found.")
        return redirect("expenses:list")

    initial = {
        "expense_scope": record["expense_scope"],
        "category": record["category"],
        "supplier_id": record["supplier_id"] or "",
        "tour_id": record["tour_id"] or "",
        "amount": record["amount"],
        "currency": record["currency"],
        "description": record["description"],
        "expense_date": record["expense_date"].date() if record["expense_date"] else None,
        "due_date": record["due_date"].date() if record["due_date"] else None,
        "receipt_file": record["receipt_file"] or "",
    }
    form = ExpenseForm(request.POST or None, initial=initial, **options)
    if request.method == "POST" and form.is_valid():
        try:
            service.update(id, actor_id=get_session_user(request)["id"], **_form_payload(form))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f"Updated {record['number']}.")
            return redirect("expenses:detail", id=id)
    return render(
        request,
        "expenses/form.html",
        {
            "form": form,
            "page_title": f"Edit {record['number']}",
            "page_heading": f"Edit {record['number']}",
            "submit_label": "Save changes",
            "record": record,
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
@require_POST
def expense_delete(request, id):
    try:
        ExpenseService().soft_delete(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as exc:
        messages.error(request, exc.message)
        return redirect("expenses:detail", id=id)
    messages.success(request, "Expense deleted.")
    return redirect("expenses:list")
