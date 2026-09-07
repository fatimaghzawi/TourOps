from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from apps.receipts.services import ReceiptService, present_receipt
from core.access import ALL_ROLES, can_access_finance
from core.constants import Collections, UserRole
from core.database import get_collection
from core.exceptions import TourOpsError
from core.permissions import login_required, role_required
from core.utils import full_name, parse_object_id


def _fmt_date(value):
    if not value:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _row(doc: dict) -> dict:
    presented = present_receipt(doc)
    customer_name = "—"
    invoice_number = "—"
    payment_number = "—"
    if doc.get("customer_id"):
        try:
            customer = get_collection(Collections.CUSTOMERS).find_one(
                {"_id": parse_object_id(doc["customer_id"], field="customer_id"), "is_deleted": {"$ne": True}}
            )
            if customer:
                customer_name = full_name(customer.get("first_name"), customer.get("last_name")) or customer.get("email") or "—"
        except TourOpsError:
            pass
    if doc.get("invoice_id"):
        try:
            invoice = get_collection(Collections.INVOICES).find_one(
                {"_id": parse_object_id(doc["invoice_id"], field="invoice_id"), "is_deleted": {"$ne": True}}
            )
            invoice_number = (invoice or {}).get("invoice_number") or "—"
        except TourOpsError:
            pass
    if doc.get("payment_id"):
        try:
            payment = get_collection(Collections.PAYMENTS).find_one(
                {"_id": parse_object_id(doc["payment_id"], field="payment_id"), "is_deleted": {"$ne": True}}
            )
            payment_number = (payment or {}).get("payment_number") or "—"
        except TourOpsError:
            pass
    return {
        **presented,
        "number": presented.get("receipt_number"),
        "customer": customer_name,
        "invoice": invoice_number,
        "payment": payment_number,
        "issued": _fmt_date(presented.get("issued_at")),
        "method": presented.get("payment_method"),
        "by": "System",
    }


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def receipt_list(request):
    rows = [_row(doc) for doc in ReceiptService().repository.list_receipts()]
    return render(
        request,
        "receipts/list.html",
        {"page_title": "Receipts", "page_heading": "Receipts", "receipts": rows},
    )


@login_required
@role_required(*ALL_ROLES)
def receipt_detail(request, id):
    try:
        doc = ReceiptService().repository.find_by_id(id)
    except TourOpsError as extra:
        raise Http404("Receipt not found.") from extra
    if not doc:
        raise Http404("Receipt not found.")
    record = _row(doc)
    crumbs = []
    if can_access_finance(request):
        crumbs.append({"label": "Receipts", "url": reverse("receipts:list")})
    crumbs.append({"label": record["number"], "url": ""})
    return render(
        request,
        "receipts/detail.html",
        {
            "page_title": record["number"],
            "page_heading": record["number"],
            "crumbs": crumbs,
            "record": record,
        },
    )
