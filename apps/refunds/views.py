from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.payments.services import PaymentService, present_payment
from apps.refunds.forms import RefundRequestForm
from apps.refunds.services import RefundService, present_refund
from core.access import OWNER_ROLES, is_owner
from core.constants import Collections, PaymentRecordStatus, UserRole
from core.database import get_collection
from core.exceptions import TourOpsError
from core.money import ZERO
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


def _payment_number(payment_id) -> str:
    if not payment_id:
        return "—"
    try:
        payment = get_collection(Collections.PAYMENTS).find_one(
            {"_id": parse_object_id(payment_id, field="payment_id"), "is_deleted": {"$ne": True}}
        )
    except TourOpsError:
        return "—"
    return (payment or {}).get("payment_number") or "—"


def _row(doc: dict) -> dict:
    presented = present_refund(doc)
    original = 0
    if doc.get("payment_id"):
        try:
            payment = get_collection(Collections.PAYMENTS).find_one(
                {"_id": doc["payment_id"], "is_deleted": {"$ne": True}}
            )
            original = payment.get("amount", 0) if payment else 0
        except Exception:
            original = 0
    return {
        **presented,
        "number": presented.get("refund_number"),
        "customer": _customer_name(presented.get("customer_id") or doc.get("customer_id")),
        "payment": _payment_number(presented.get("payment_id") or doc.get("payment_id")),
        "booking": presented.get("booking_id") or "—",
        "requested": _fmt_date(doc.get("created_at")),
        "approver": "—",
        "original": original,
        "already": 0,
        "refundable": presented.get("amount"),
        "reason": presented.get("reason") or "—",
    }


def _payment_choices(service: RefundService) -> list[tuple[str, str]]:
    choices = []
    for doc in PaymentService().repository.list_payments():
        if doc.get("status") != PaymentRecordStatus.COMPLETED.value:
            continue
        remaining = service.remaining_refundable(doc)
        if remaining <= ZERO:
            continue
        presented = present_payment(doc)
        customer = _customer_name(presented.get("customer_id") or doc.get("customer_id"))
        label = f"{presented.get('payment_number')} · {customer} · {remaining} remaining"
        choices.append((presented["id"], label))
    return choices


def _locked_payment(service: RefundService, payment_id: str) -> dict | None:
    if not payment_id:
        return None
    try:
        doc = PaymentService().repository.find_by_id(payment_id)
    except TourOpsError:
        return None
    if not doc:
        return None
    presented = present_payment(doc)
    remaining = service.remaining_refundable(doc)
    return {
        **presented,
        "number": presented.get("payment_number"),
        "customer": _customer_name(presented.get("customer_id") or doc.get("customer_id")),
        "remaining": remaining,
        "can_refund": (
            presented.get("status") == PaymentRecordStatus.COMPLETED.value and remaining > ZERO
        ),
    }


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def refund_list(request):
    rows = [_row(doc) for doc in RefundService().repository.list_refunds()]
    return render(
        request,
        "refunds/list.html",
        {"page_title": "Refunds", "page_heading": "Refunds", "refunds": rows},
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def refund_create(request):
    service = RefundService()
    payment_id = (request.POST.get("payment_id") or request.GET.get("payment_id") or "").strip()
    payment = _locked_payment(service, payment_id)
    choices = _payment_choices(service)
    if payment and payment["id"] not in {item[0] for item in choices}:
        choices = [(payment["id"], f"{payment['number']} · {payment['customer']}")] + choices
    lock = bool(payment_id and payment)
    remaining = payment["remaining"] if payment else None
    form = RefundRequestForm(
        request.POST or None,
        payment_choices=choices,
        lock_payment=lock,
        remaining=remaining,
        initial={"payment_id": payment_id, "policy_tier": "AGENCY_CANCEL"} if payment_id else {"policy_tier": "AGENCY_CANCEL"},
    )
    if request.method == "POST" and form.is_valid():
        direct = is_owner(request)
        try:
            refund = service.create_from_payment(
                form.cleaned_data["payment_id"],
                reason=form.cleaned_data["reason"],
                refund_method=form.cleaned_data["refund_method"],
                tier=form.cleaned_data["policy_tier"],
                amount=form.cleaned_data.get("amount"),
                requested_by=request.user.actor_id,
                direct=direct,
            )
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            if direct:
                messages.success(request, f"Refunded {refund.get('refund_number')}. The original payment is unchanged.")
            else:
                messages.success(request, f"Requested {refund.get('refund_number')}. Approve it to pay out.")
            return redirect("refunds:detail", id=refund["id"])
    elif request.method == "POST":
        messages.error(request, "Check the refund details and try again.")
    if payment_id and not payment:
        messages.error(request, "Payment not found.")
    elif payment and not payment["can_refund"] and request.method == "GET":
        messages.error(request, "This payment has nothing left to refund.")
    owner = is_owner(request)
    return render(
        request,
        "refunds/form.html",
        {
            "form": form,
            "payment": payment if payment and payment.get("can_refund") else payment,
            "direct_refund": owner,
            "can_decide": owner,
            "page_title": "Issue refund" if owner else "Request refund",
            "page_heading": "Issue refund" if owner else "Request refund",
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def refund_detail(request, id):
    try:
        doc = RefundService()._get_raw(id)
    except TourOpsError as extra:
        raise Http404("Refund not found.") from extra
    record = _row(doc)
    return render(
        request,
        "refunds/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": [
                {"label": "Refunds", "url": reverse("refunds:list")},
                {"label": record["number"], "url": ""},
            ],
            "record": record,
            "can_decide": is_owner(request),
        },
    )


def _act(request, id, action):
    service = RefundService()
    try:
        if action == "approve":
            service.approve(id, actor_id=request.user.actor_id)
            messages.success(request, "Refund approved.")
        elif action == "reject":
            service.reject(id, actor_id=request.user.actor_id)
            messages.success(request, "Refund rejected. The original payment is unchanged.")
        elif action == "complete":
            service.complete(id, actor_id=request.user.actor_id)
            messages.success(request, "Refund marked completed.")
    except TourOpsError as extra:
        messages.error(request, extra.message)
    return redirect("refunds:detail", id=id)


@login_required
@role_required(*OWNER_ROLES)
@require_POST
def refund_approve(request, id):
    return _act(request, id, "approve")


@login_required
@role_required(*OWNER_ROLES)
@require_POST
def refund_reject(request, id):
    return _act(request, id, "reject")


@login_required
@role_required(*OWNER_ROLES)
@require_POST
def refund_complete(request, id):
    return _act(request, id, "complete")
