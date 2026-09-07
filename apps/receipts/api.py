"""JSON API — receipts.  OWNER: Dev 3 — Customer Finance

Receipts are auto-created when a payment completes. There is no POST.
"""
from apps.receipts.services import ReceiptService
from core.http import guarded, query_value, resource_id
from core.responses import success_response


@guarded
def list_receipts(request, **kwargs):
    items = ReceiptService().list_items(
        customer_id=query_value(request, "customer_id"),
        payment_id=query_value(request, "payment_id"),
        invoice_id=query_value(request, "invoice_id"),
    )
    return success_response({"receipts": items})


@guarded
def get_receipt(request, **kwargs):
    return success_response(ReceiptService().get(resource_id(kwargs)))


@guarded
def receipt_for_payment(request, **kwargs):
    return success_response(ReceiptService().for_payment(resource_id(kwargs, "id", "payment_id")))
