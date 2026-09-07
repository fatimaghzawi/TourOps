from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.expenses.services import ExpenseService
from apps.supplier_payments.forms import SupplierPaymentForm
from apps.supplier_payments.services import SupplierPaymentService
from apps.suppliers.constants import PREFERRED_METHOD_LABELS, PREFERRED_METHODS
from apps.suppliers.services import SupplierService
from core.access import FINANCE_ROLES
from core.exceptions import DatabaseUnavailableError, NotFoundError, TourOpsError
from core.permissions import get_session_user, login_required, role_required
from core.utils import utcnow


def _unavailable(request):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect("supplier_payments:list")


def _form_payload(form: SupplierPaymentForm) -> dict:
    return {
        "expense_id": form.cleaned_data["expense_id"],
        "amount": form.cleaned_data["amount"],
        "payment_method": form.cleaned_data["payment_method"],
        "payment_date": form.cleaned_data["payment_date"],
        "reference_number": form.cleaned_data.get("reference_number"),
        "notes": form.cleaned_data.get("notes"),
        "currency": form.cleaned_data.get("currency"),
    }


def _bill(expense_id):
    if not expense_id:
        return None
    try:
        return ExpenseService().get_presented(expense_id)
    except (NotFoundError, TourOpsError):
        return None


def _supplier_preference(bill, supplier_id):
    sid = supplier_id or (bill.get("supplier_id") if bill else None)
    if not sid:
        return None, ""
    try:
        supplier = SupplierService().get_presented(sid, include_extras=False)
    except (NotFoundError, TourOpsError, DatabaseUnavailableError):
        return None, ""
    method = supplier.get("preferred_payment_method") or None
    if method not in PREFERRED_METHODS:
        return None, ""
    return method, PREFERRED_METHOD_LABELS.get(method, "")


@login_required
@role_required(*FINANCE_ROLES)
def supplier_payment_list(request):
    service = SupplierPaymentService()
    expense_id = (request.GET.get("expense_id") or "").strip()
    try:
        payments = service.list_presented(expense_id=expense_id or None)
        bill = _bill(expense_id) if expense_id else None
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Supplier payments are unavailable.")
        payments, bill = [], None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        payments, bill = [], None
    return render(
        request,
        "supplier_payments/list.html",
        {
            "page_title": "Supplier payments",
            "page_heading": "Supplier payments",
            "payments": payments,
            "bill": bill,
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
@require_http_methods(["GET", "POST"])
def supplier_payment_create(request):
    service = SupplierPaymentService()
    expense_id = (request.POST.get("expense_id") or request.GET.get("expense_id") or "").strip()
    try:
        bill = _bill(expense_id)
        if bill and not bill["has_remaining"]:
            messages.info(request, f"{bill['number']} is already paid in full.")
            return redirect("expenses:detail", id=bill["id"])
        choices = service.open_expense_choices(
            supplier_id=request.GET.get("supplier_id") or None,
            include_id=expense_id or None,
        )
    except DatabaseUnavailableError:
        return _unavailable(request)

    if not choices and request.method != "POST":
        return render(
            request,
            "supplier_payments/form.html",
            {
                "form": None,
                "bill": bill,
                "preferred_label": "",
                "page_title": "Record supplier payment",
                "page_heading": "Record supplier payment",
            },
        )

    remaining = bill["remaining"] if bill else None
    preferred, preferred_label = _supplier_preference(bill, request.GET.get("supplier_id"))
    initial = {
        "payment_date": utcnow().date(),
        "payment_method": preferred or "BANK_TRANSFER",
    }
    if bill:
        initial["expense_id"] = bill["id"]
        initial["currency"] = bill["currency"]
        initial["amount"] = bill["remaining"]
    form = SupplierPaymentForm(
        request.POST or None,
        initial=initial,
        expense_choices=choices,
        lock_expense=bool(bill),
        remaining=remaining,
    )
    if request.method == "POST" and form.is_valid():
        try:
            payment = service.create(actor_id=get_session_user(request)["id"], **_form_payload(form))
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Recorded {payment['supplier_payment_number']}.")
            return redirect("supplier_payments:detail", id=str(payment["_id"]))
    return render(
        request,
        "supplier_payments/form.html",
        {
            "form": form,
            "bill": bill,
            "preferred_label": preferred_label,
            "page_title": "Record supplier payment",
            "page_heading": "Record supplier payment",
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
def supplier_payment_detail(request, id):
    try:
        record = SupplierPaymentService().get_presented(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Supplier payment not found.")
        return redirect("supplier_payments:list")
    return render(
        request,
        "supplier_payments/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Supplier payments", "url": reverse("supplier_payments:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
        },
    )


@login_required
@role_required(*FINANCE_ROLES)
@require_POST
def supplier_payment_void(request, id):
    try:
        SupplierPaymentService().void(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("supplier_payments:detail", id=id)
    messages.success(request, "Supplier payment voided.")
    return redirect("supplier_payments:list")
