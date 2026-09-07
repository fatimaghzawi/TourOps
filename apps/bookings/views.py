from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.bookings.forms import BookingForm
from apps.bookings.services import BookingService
from apps.customers.services import CustomerService
from apps.invoices.repositories import InvoiceRepository
from apps.invoices.services import InvoiceService, present_invoice
from apps.payments.forms import DeskPaymentForm
from apps.payments.services import PaymentService
from apps.receipts.services import ReceiptService
from apps.tours.services import TourService
from core.access import ALL_ROLES, OPERATIONS_ROLES, can_access_operations
from core.exceptions import BusinessRuleViolation, DatabaseUnavailableError, NotFoundError, TourOpsError
from core.money import ZERO, to_money
from core.permissions import get_session_user, login_required, role_required


def _unavailable(request):
    messages.error(request, "Cannot reach MongoDB. Check MONGODB_URI and that MongoDB is running.")
    return redirect("bookings:list")


def _desk(booking_id) -> dict:
    repo = InvoiceRepository()
    raw = repo.find_by_booking(booking_id) or repo.find_by_booking(booking_id, include_cancelled=True)
    invoice = present_invoice(raw) if raw else None
    payments = []
    if invoice:
        for payment in PaymentService().for_invoice(invoice["id"]):
            receipt = None
            try:
                receipt = ReceiptService().for_payment(payment["id"])
            except NotFoundError:
                receipt = None
            payments.append({**payment, "receipt": receipt})
    remaining = to_money(invoice.get("remaining_amount") or 0) if invoice else ZERO
    can_pay = bool(
        invoice
        and invoice.get("status") != "CANCELLED"
        and remaining > ZERO
    )
    return {
        "invoice": invoice,
        "payments": payments,
        "remaining": remaining,
        "can_pay": can_pay,
        "pay_form": DeskPaymentForm(remaining=remaining) if can_pay else None,
    }


def _travelers_from_post(post) -> list[dict]:
    people = []
    for index in range(8):
        first = (post.get(f"traveler_{index}_first") or "").strip()
        last = (post.get(f"traveler_{index}_last") or "").strip()
        if not first and not last:
            continue
        people.append(
            {
                "first_name": first,
                "last_name": last,
                "passport_number": (post.get(f"traveler_{index}_passport") or "").strip(),
                "nationality": (post.get(f"traveler_{index}_nationality") or "").strip(),
            }
        )
    return people


def _guest_form_rows(post=None) -> list[dict]:
    rows = []
    last_filled = 0
    for index in range(8):
        first = (post.get(f"traveler_{index}_first") if post else "") or ""
        last = (post.get(f"traveler_{index}_last") if post else "") or ""
        passport = (post.get(f"traveler_{index}_passport") if post else "") or ""
        nationality = (post.get(f"traveler_{index}_nationality") if post else "") or ""
        filled = bool(
            str(first).strip() or str(last).strip() or str(passport).strip() or str(nationality).strip()
        )
        if filled:
            last_filled = index
        rows.append(
            {
                "index": index,
                "n": f"{index + 1:02d}",
                "first": first,
                "last": last,
                "passport": passport,
                "nationality": nationality,
            }
        )
    visible = min(max((last_filled + 1) if post else 1, 1), 8)
    for index, row in enumerate(rows):
        row["hidden"] = index >= visible
    return rows


@login_required
@role_required(*OPERATIONS_ROLES)
def booking_list(request):
    status = (request.GET.get("status") or "").strip().upper() or None
    try:
        bookings = BookingService().list_presented()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Bookings are unavailable.")
        bookings = []
    except TourOpsError as extra:
        messages.error(request, extra.message)
        bookings = []
    return render(
        request,
        "bookings/list.html",
        {
            "page_title": "Bookings",
            "page_heading": "Bookings",
            "bookings": bookings,
            "status_filter": status or "",
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_http_methods(["GET", "POST"])
def booking_create(request):
    try:
        customers = CustomerService().list_options()
        tours = []
        for row in TourService().list_presented():
            label = f"{row['name']} · {row['available']} seats left"
            if not row.get("can_take_bookings"):
                label += " · waiting on suppliers"
            tours.append((row["id"], label))
    except DatabaseUnavailableError:
        return _unavailable(request)
    initial = {}
    if request.GET.get("tour_id"):
        initial["tour_id"] = request.GET.get("tour_id")
        try:
            TourService().assert_ready_for_customer_bookings(request.GET.get("tour_id"))
        except BusinessRuleViolation as extra:
            messages.warning(request, extra.message)
        except TourOpsError:
            pass
    if request.GET.get("customer_id"):
        initial["customer_id"] = request.GET.get("customer_id")
    form = BookingForm(
        request.POST or None,
        initial=initial or None,
        customer_choices=customers,
        tour_choices=tours,
    )
    if request.method == "POST" and form.is_valid():
        try:
            booking = BookingService().create(
                actor_id=get_session_user(request)["id"],
                customer_id=form.cleaned_data["customer_id"],
                tour_id=form.cleaned_data["tour_id"],
                travelers=_travelers_from_post(request.POST),
                notes=form.cleaned_data.get("notes"),
            )
            if (request.POST.get("action") or "") == "confirm":
                booking = BookingService().confirm(booking["_id"], actor_id=get_session_user(request)["id"])
                messages.success(
                    request,
                    f"{booking['booking_number']} confirmed. Collect payment below.",
                )
            else:
                messages.success(request, f"Created {booking['booking_number']} as pending.")
        except DatabaseUnavailableError:
            return _unavailable(request)
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            return redirect("bookings:detail", id=str(booking["_id"]))
    return render(
        request,
        "bookings/create.html",
        {
            "form": form,
            "page_title": "New booking",
            "page_heading": "New booking",
            "traveler_rows": _guest_form_rows(request.POST if request.method == "POST" else None),
        },
    )


@login_required
@role_required(*ALL_ROLES)
def booking_detail(request, id):
    try:
        record = BookingService().get_presented(id)
        desk = _desk(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Booking not found.")
        if can_access_operations(request):
            return redirect("bookings:list")
        return redirect("invoices:list")
    crumbs = []
    if can_access_operations(request):
        crumbs.append({"label": "Bookings", "url": reverse("bookings:list")})
    crumbs.append({"label": record["number"], "url": ""})
    return render(
        request,
        "bookings/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": crumbs,
            "record": record,
            **desk,
        },
    )


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def booking_confirm(request, id):
    try:
        BookingService().confirm(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("bookings:detail", id=id)
    messages.success(request, "Booking confirmed. Collect payment below.")
    return redirect("bookings:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def booking_complete(request, id):
    try:
        BookingService().complete(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("bookings:detail", id=id)
    messages.success(request, "Booking marked completed.")
    return redirect("bookings:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def booking_cancel(request, id):
    try:
        BookingService().cancel(id, actor_id=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("bookings:detail", id=id)
    messages.success(request, "Booking cancelled. Confirmed seats were returned to the tour.")
    return redirect("bookings:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def booking_invoice(request, id):
    try:
        invoice = InvoiceService().create_for_booking(id, created_by=get_session_user(request)["id"])
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("bookings:detail", id=id)
    messages.success(request, f"Invoice {invoice.get('invoice_number')} is ready. Collect payment below.")
    return redirect("bookings:detail", id=id)


@login_required
@role_required(*OPERATIONS_ROLES)
@require_POST
def booking_pay(request, id):
    try:
        desk = _desk(id)
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError:
        messages.error(request, "Booking not found.")
        return redirect("bookings:list")
    if not desk["can_pay"]:
        messages.error(request, "There is nothing left to collect on this booking.")
        return redirect("bookings:detail", id=id)
    form = DeskPaymentForm(request.POST, remaining=desk["remaining"])
    if not form.is_valid():
        messages.error(request, "Check the payment amount and method, then try again.")
        return redirect("bookings:detail", id=id)
    try:
        payment = PaymentService().record_for_invoice(
            desk["invoice"]["id"],
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            reference_number=form.cleaned_data["reference_number"] or None,
            recorded_by=get_session_user(request)["id"],
        )
    except DatabaseUnavailableError:
        return _unavailable(request)
    except TourOpsError as extra:
        messages.error(request, extra.message)
        return redirect("bookings:detail", id=id)
    messages.success(request, f"Recorded {payment.get('payment_number')}. Receipt issued.")
    return redirect("bookings:detail", id=id)
