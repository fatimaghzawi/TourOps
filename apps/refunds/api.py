"""JSON API — refunds.  OWNER: Dev 3 — Customer Finance"""
from apps.refunds.services import RefundService
from core.access import is_owner
from core.exceptions import ValidationError
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _create(request, payment_id, payload):
    return RefundService().create_from_payment(
        payment_id,
        reason=payload.get("reason") or "",
        refund_method=payload.get("refund_method") or payload.get("method") or "CASH",
        tier=payload.get("policy_tier"),
        days_before=payload.get("days_before"),
        amount=payload.get("amount"),
        requested_by=actor_id(request),
        direct=is_owner(request),
    )


@guarded
def list_refunds(request, **kwargs):
    items = RefundService().list_items(
        customer_id=query_value(request, "customer_id"),
        status=query_value(request, "status"),
        payment_id=query_value(request, "payment_id"),
    )
    return success_response({"refunds": items})


@guarded
def create_refund(request, **kwargs):
    payload = json_body(request)
    payment_id = payload.get("payment_id")
    if not payment_id:
        raise ValidationError("payment_id is required.")
    return success_response(_create(request, payment_id, payload), status=201)


@guarded
def get_refund(request, **kwargs):
    return success_response(RefundService().get(resource_id(kwargs)))


@guarded
def refund_from_payment(request, **kwargs):
    payload = json_body(request)
    refund = _create(request, resource_id(kwargs, "id", "payment_id"), payload)
    return success_response(refund, status=201)


@guarded
def approve_refund(request, **kwargs):
    return success_response(RefundService().approve(resource_id(kwargs), actor_id=actor_id(request)))


@guarded
def reject_refund(request, **kwargs):
    return success_response(RefundService().reject(resource_id(kwargs), actor_id=actor_id(request)))


@guarded
def complete_refund(request, **kwargs):
    return success_response(RefundService().complete(resource_id(kwargs), actor_id=actor_id(request)))
