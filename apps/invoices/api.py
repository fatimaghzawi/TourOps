"""JSON API — invoices.  OWNER: Dev 3 — Customer Finance"""
from apps.invoices.services import InvoiceService
from core.exceptions import ValidationError
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


@guarded
def list_invoices(request, **kwargs):
    items = InvoiceService().list_items(
        customer_id=query_value(request, "customer_id"),
        status=query_value(request, "status"),
        booking_id=query_value(request, "booking_id"),
    )
    return success_response({"invoices": items})


@guarded
def create_invoice(request, **kwargs):
    payload = json_body(request)
    booking_id = payload.get("booking_id")
    if not booking_id:
        raise ValidationError("booking_id is required.")
    invoice = InvoiceService().create_for_booking(booking_id, created_by=actor_id(request))
    return success_response(invoice, status=201)


@guarded
def get_invoice(request, **kwargs):
    return success_response(InvoiceService().get(resource_id(kwargs)))


@guarded
def cancel_invoice(request, **kwargs):
    invoice = InvoiceService().cancel(resource_id(kwargs), actor_id=actor_id(request))
    return success_response(invoice)


@guarded
def patch_invoice(request, **kwargs):
    payload = json_body(request)
    if payload.get("action") == "cancel":
        return cancel_invoice(request, **kwargs)
    raise ValidationError('Unsupported patch. Send {"action": "cancel"} or POST .../cancel/.')


@guarded
def create_invoice_for_booking(request, **kwargs):
    invoice = InvoiceService().create_for_booking(
        resource_id(kwargs, "booking_id", "id"),
        created_by=actor_id(request),
    )
    return success_response(invoice, status=201)
