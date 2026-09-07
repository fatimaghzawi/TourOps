"""JSON API — payments.  OWNER: Dev 3 — Customer Finance"""
from apps.payments.services import PaymentService
from core.exceptions import ValidationError
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _record(request, invoice_id, payload):
    return PaymentService().record_for_invoice(
        invoice_id,
        amount=payload.get("amount"),
        method=payload.get("payment_method") or payload.get("method"),
        reference_number=payload.get("reference_number") or payload.get("ref"),
        notes=payload.get("notes"),
        recorded_by=actor_id(request),
    )


@guarded
def list_payments(request, **kwargs):
    items = PaymentService().list_items(
        invoice_id=query_value(request, "invoice_id"),
        customer_id=query_value(request, "customer_id"),
    )
    return success_response({"payments": items})


@guarded
def create_payment(request, **kwargs):
    payload = json_body(request)
    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        raise ValidationError("invoice_id is required.")
    return success_response(_record(request, invoice_id, payload), status=201)


@guarded
def get_payment(request, **kwargs):
    return success_response(PaymentService().get(resource_id(kwargs, "id", "payment_id")))


@guarded
def payments_for_invoice(request, **kwargs):
    items = PaymentService().for_invoice(resource_id(kwargs, "id", "invoice_id"))
    return success_response({"payments": items})


@guarded
def create_payment_for_invoice(request, **kwargs):
    payload = json_body(request)
    payment = _record(request, resource_id(kwargs, "id", "invoice_id"), payload)
    return success_response(payment, status=201)


@guarded
def void_payment(request, **kwargs):
    result = PaymentService().void(
        resource_id(kwargs, "id", "payment_id"),
        actor_id=actor_id(request),
    )
    return success_response(result)
