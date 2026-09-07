from datetime import datetime, timezone

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.bookings.services import BookingService
from apps.invoices.services import InvoiceService, present_invoice
from apps.payments.forms import DeskPaymentForm
from apps.payments.services import PaymentService
from core.constants import BookingStatus, InvoiceStatus, UserRole
from core.exceptions import NotFoundError, TourOpsError
from core.money import ZERO, to_decimal
from core.permissions import login_required, role_required
from core.utils import serialize_id

STATUS_TABS = [
    ("", "All Statuses"),
    (InvoiceStatus.ISSUED.value, "Issued"),
    (InvoiceStatus.PARTIALLY_PAID.value, "Partially Paid"),
    (InvoiceStatus.PAID.value, "Paid"),
    (InvoiceStatus.PARTIALLY_REFUNDED.value, "Partially Refunded"),
    (InvoiceStatus.REFUNDED.value, "Refunded"),
    (InvoiceStatus.CANCELLED.value, "Cancelled"),
]

COLLECTABLE = {InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIALLY_PAID.value}


def _fmt_date(value):
    if not value:
        return "--"
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    return str(value)


def _is_overdue(inv: dict) -> bool:
    if inv.get("status") not in COLLECTABLE:
        return False
    due = inv.get("due_date")
    if not isinstance(due, datetime):
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due < datetime.now(timezone.utc)


def _row(inv: dict) -> dict:
    remaining = to_decimal(inv.get("remaining_amount") or 0)
    paid = to_decimal(inv.get("paid_amount") or 0)
    refunded = to_decimal(inv.get("refunded_amount") or 0)
    status = inv.get("status")
    live = status != InvoiceStatus.CANCELLED.value
    return {
        "id": inv["id"],
        "number": inv["invoice_number"],
        "customer": inv.get("customer_name") or "--",
        "customer_id": inv.get("customer_id"),
        "booking": inv.get("booking_number") or "--",
        "booking_id": inv.get("booking_id"),
        "issue": _fmt_date(inv.get("issue_date")),
        "due": _fmt_date(inv.get("due_date")),
        "total": inv.get("total_amount"),
        "paid": inv.get("paid_amount"),
        "remaining": inv.get("remaining_amount"),
        "status": status,
        "overdue": _is_overdue(inv),
        "can_pay": status in COLLECTABLE and remaining > ZERO,
        "can_cancel": live and (paid - refunded) <= ZERO,
    }


def _require_invoice(invoice_id: str) -> dict:
    try:
        return InvoiceService()._get_raw(invoice_id)
    except (NotFoundError, TourOpsError) as extra:
        raise Http404("Invoice not found.") from extra


def _detail_record(raw: dict) -> dict:
    inv = present_invoice(raw)
    items = [
        {
            "description": line.get("description", ""),
            "quantity": line.get("quantity", 1),
            "unit_price": line.get("unit_price", 0),
            "total": line.get("total", 0),
        }
        for line in raw.get("line_items", [])
    ]
    discount = raw.get("discount", {}) or {}
    tax = raw.get("tax", {}) or {}
    remaining = to_decimal(inv.get("remaining_amount") or 0)
    paid = to_decimal(inv.get("paid_amount") or 0)
    refunded = to_decimal(inv.get("refunded_amount") or 0)
    status = inv["status"]
    live = status != InvoiceStatus.CANCELLED.value
    return {
        "id": inv["id"],
        "number": inv["invoice_number"],
        "status": status,
        "customer": inv.get("customer_name") or "--",
        "customer_id": inv.get("customer_id"),
        "customer_email": inv.get("customer_email") or "",
        "booking": inv.get("booking_number") or "--",
        "booking_id": inv.get("booking_id"),
        "issue": _fmt_date(raw.get("issue_date")),
        "due": _fmt_date(raw.get("due_date")),
        "items": items,
        "subtotal": inv.get("subtotal"),
        "discount_amount": discount.get("amount", 0),
        "tax_rate": tax.get("rate", 0),
        "tax_amount": tax.get("amount", 0),
        "total": inv.get("total_amount"),
        "paid": inv.get("paid_amount"),
        "remaining": inv.get("remaining_amount"),
        "overdue": _is_overdue(raw),
        "can_pay": status in COLLECTABLE and remaining > ZERO,
        "can_cancel": live and (paid - refunded) <= ZERO,
        "can_reissue": (live and (paid - refunded) <= ZERO) or status == InvoiceStatus.CANCELLED.value,
    }


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def invoice_list(request):
    status = request.GET.get("status") or None
    service = InvoiceService()
    invoices = service.list_items()
    all_rows = [_row(item) for item in invoices]
    rows = [row for row in all_rows if (not status) or row["status"] == status]

    counts = {value: 0 for value, _ in STATUS_TABS}
    counts[""] = len(all_rows)
    for row in all_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return render(
        request,
        "invoices/list.html",
        {
            "page_title": "Invoices",
            "page_heading": "Invoices",
            "rows": rows,
            "status_tabs": [
                {"value": value, "label": label, "count": counts.get(value, 0), "active": (status or "") == value}
                for value, label in STATUS_TABS
            ],
            "search": request.GET.get("q", ""),
            "total_count": len(all_rows),
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def invoice_detail(request, id):
    raw = _require_invoice(id)
    record = _detail_record(raw)
    remaining = to_decimal(record.get("remaining") or 0)
    payments = PaymentService().for_invoice(id)
    return render(
        request,
        "invoices/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Invoices", "url": reverse("invoices:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "payments": payments,
            "pay_form": DeskPaymentForm(remaining=remaining) if record["can_pay"] else None,
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def invoice_print(request, id):
    raw = _require_invoice(id)
    inv = present_invoice(raw)
    record = {**_detail_record(raw), **inv, "number": inv["invoice_number"]}
    return render(
        request,
        "invoices/print.html",
        {
            "page_title": "Print " + record["number"],
            "page_heading": record["number"],
            "record": record,
        },
    )


def _invoicable_bookings() -> list[dict]:
    invoiced = {
        serialize_id(invoice.get("booking_id"))
        for invoice in InvoiceService().list_items()
        if invoice.get("status") != InvoiceStatus.CANCELLED.value
    }
    rows = []
    invoicable = list(BookingService().list_presented(status=BookingStatus.CONFIRMED.value))
    invoicable.extend(BookingService().list_presented(status=BookingStatus.COMPLETED.value))
    for booking in invoicable:
        if booking["id"] in invoiced:
            continue
        rows.append(
            {
                "id": booking["id"],
                "number": booking.get("booking_number") or booking.get("number"),
                "customer": booking.get("customer"),
                "tour": booking.get("tour"),
                "travelers": booking.get("travelers_count"),
                "amount": booking.get("total"),
                "avatar": "#2563EB",
            }
        )
    return rows


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def invoice_create(request):
    return render(
        request,
        "invoices/create.html",
        {
            "page_title": "Create Invoice",
            "page_heading": "Create Invoice",
            "bookings": _invoicable_bookings(),
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_POST
def invoice_from_booking(request, booking_id):
    try:
        invoice = InvoiceService().create_for_booking(booking_id, created_by=request.user.actor_id)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("invoices:create")
    messages.success(request, f"Issued {invoice.get('invoice_number')}.")
    return redirect("invoices:detail", id=invoice["id"])


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_POST
def invoice_pay(request, id):
    record = _detail_record(_require_invoice(id))
    if not record["can_pay"]:
        messages.error(request, "There is nothing left to collect on this invoice.")
        return redirect("invoices:detail", id=id)
    form = DeskPaymentForm(request.POST, remaining=to_decimal(record.get("remaining") or 0))
    if not form.is_valid():
        messages.error(request, "Check the payment amount and method, then try again.")
        return redirect("invoices:detail", id=id)
    try:
        payment = PaymentService().record_for_invoice(
            id,
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            reference_number=form.cleaned_data["reference_number"] or None,
            recorded_by=request.user.actor_id,
        )
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("invoices:detail", id=id)
    messages.success(request, f"Recorded {payment.get('payment_number')}. Receipt issued.")
    return redirect("invoices:detail", id=id)


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_POST
def invoice_cancel(request, id):
    try:
        InvoiceService().cancel(id, actor_id=request.user.actor_id)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("invoices:detail", id=id)
    messages.success(request, "Invoice cancelled.")
    return redirect("invoices:detail", id=id)


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def invoice_reissue(request, id):
    record = _detail_record(_require_invoice(id))
    if request.method == "POST":
        if not record["can_reissue"]:
            messages.error(request, "Refund any collected money before cancelling and reissuing this invoice.")
            return redirect("invoices:detail", id=id)
        try:
            invoice = InvoiceService().reissue(id, actor_id=request.user.actor_id)
        except TourOpsError as extra:
            messages.error(request, extra.message)
            return redirect("invoices:detail", id=id)
        messages.success(request, f"Issued {invoice.get('invoice_number')} in place of {record['number']}.")
        return redirect("invoices:detail", id=invoice["id"])
    return render(
        request,
        "invoices/reissue.html",
        {
            "page_title": "Reissue " + record["number"],
            "page_heading": record["number"],
            "record": record,
        },
    )
