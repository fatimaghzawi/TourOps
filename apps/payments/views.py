from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.invoices.services import InvoiceService
from apps.payments.forms import PaymentForm
from apps.payments.services import PaymentService, present_payment
from apps.receipts.services import ReceiptService
from apps.refunds.services import RefundService
from core.constants import Collections, UserRole
from core.database import get_collection
from core.exceptions import NotFoundError, TourOpsError
from core.money import ZERO, to_decimal, to_money
from core.permissions import login_required, role_required
from core.utils import full_name, parse_object_id


def _fmt_date(value):
    if not value:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _customer_name(customer_id) -> str:
    if not customer_id:
        return "—"
    try:
        customer = get_collection(Collections.CUSTOMERS).find_one(
            {"_id": parse_object_id(customer_id, field="customer_id"), "is_deleted": {"$ne": True}}
        )
    except TourOpsError:
        return "—"
    if not customer:
        return "—"
    return full_name(customer.get("first_name"), customer.get("last_name")) or customer.get("email") or "—"


def _invoice_number(invoice_id) -> str:
    if not invoice_id:
        return "—"
    try:
        invoice = InvoiceService().get(invoice_id)
    except TourOpsError:
        return "—"
    return invoice.get("invoice_number") or "—"


def _row(doc: dict) -> dict:
    presented = present_payment(doc)
    return {
        **presented,
        "number": presented.get("payment_number"),
        "invoice": _invoice_number(presented.get("invoice_id")),
        "customer": _customer_name(presented.get("customer_id")),
        "date": _fmt_date(presented.get("payment_date")),
        "method": presented.get("payment_method"),
        "ref": presented.get("reference_number") or "—",
        "by": "Staff",
    }


def _open_invoices():
    choices = []
    for invoice in InvoiceService().list_items():
        remaining = to_decimal(invoice.get("remaining_amount") or 0)
        if remaining <= ZERO:
            continue
        if invoice.get("status") == "CANCELLED":
            continue
        label = f"{invoice.get('invoice_number')} · {invoice.get('customer_name') or 'Customer'} · {to_money(remaining)} remaining"
        choices.append((invoice["id"], label))
    return choices


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def payment_list(request):
    raw = PaymentService().repository.list_payments()
    rows = [_row(doc) for doc in raw]
    today_total = ZERO
    month_total = ZERO
    cash = ZERO
    bank = ZERO
    today = None
    for doc in raw:
        amount = to_decimal(doc.get("amount") or 0)
        when = doc.get("payment_date")
        if hasattr(when, "date"):
            if today is None:
                from core.utils import utcnow

                today = utcnow().date()
            if when.date() == today:
                today_total += amount
            if when.month == today.month and when.year == today.year:
                month_total += amount
        method = doc.get("payment_method")
        if method == "CASH":
            cash += amount
        else:
            bank += amount
    return render(
        request,
        "payments/list.html",
        {
            "page_title": "Payments",
            "page_heading": "Payment ledger",
            "payments": rows,
            "metrics": {
                "today": today_total,
                "month": month_total,
                "cash": cash,
                "bank": bank,
            },
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def payment_create(request):
    invoice_id = (request.GET.get("invoice_id") or "").strip()
    choices = _open_invoices()
    initial = {}
    if invoice_id and invoice_id in {str(item[0]) for item in choices}:
        initial["invoice_id"] = invoice_id
        try:
            remaining = to_decimal(InvoiceService().get(invoice_id).get("remaining_amount") or 0)
            if remaining > ZERO:
                initial["amount"] = remaining
        except TourOpsError:
            pass
    form = PaymentForm(request.POST or None, invoice_choices=choices, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        try:
            payment = PaymentService().record_for_invoice(
                form.cleaned_data["invoice_id"],
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                reference_number=form.cleaned_data["reference_number"] or None,
                notes=form.cleaned_data["notes"] or None,
                recorded_by=request.user.actor_id,
            )
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, f"Recorded {payment.get('payment_number')}.")
            return redirect("payments:detail", id=payment["id"])
    elif request.method == "POST":
        messages.error(request, "Check the payment details and try again.")
    return render(
        request,
        "payments/form.html",
        {"form": form, "page_title": "Record payment", "page_heading": "Record payment"},
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def payment_detail(request, id):
    try:
        doc = PaymentService().repository.find_by_id(id)
    except TourOpsError as extra:
        raise Http404("Payment not found.") from extra
    if not doc:
        raise Http404("Payment not found.")
    record = _row(doc)
    receipt_id = None
    try:
        receipt = ReceiptService().for_payment(id)
        receipt_id = receipt.get("id")
    except NotFoundError:
        receipt_id = None
    return render(
        request,
        "payments/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Payments", "url": reverse("payments:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "receipt_id": receipt_id,
            "refunds": RefundService().list_items(payment_id=id),
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_POST
def payment_void(request, id):
    try:
        PaymentService().void(id, actor_id=request.user.actor_id)
    except TourOpsError as extra:
        messages.error(request, extra.message)
    else:
        messages.success(request, "Payment voided. Invoice balances were recomputed.")
    return redirect("payments:detail", id=id)
