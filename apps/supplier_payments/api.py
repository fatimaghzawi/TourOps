from apps.supplier_payments.services import SupplierPaymentService, serialize_payment
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _fields(request, payload, **overrides):
    return {
        "actor_id": actor_id(request),
        "expense_id": payload.get("expense_id"),
        "amount": payload.get("amount"),
        "payment_method": payload.get("payment_method") or payload.get("method") or "",
        "payment_date": payload.get("payment_date"),
        "reference_number": payload.get("reference_number") or payload.get("ref"),
        "notes": payload.get("notes"),
        "currency": payload.get("currency"),
        "supplier_id": payload.get("supplier_id"),
        **overrides,
    }


def _presented(payment: dict) -> dict:
    return serialize_payment(SupplierPaymentService().get_presented(payment["_id"]))


@guarded
def list_supplier_payments(request, **kwargs):
    items = SupplierPaymentService().list_presented(
        supplier_id=query_value(request, "supplier_id"),
        expense_id=query_value(request, "expense_id"),
    )
    return success_response({"payments": [serialize_payment(item) for item in items]})


@guarded
def create_supplier_payment(request, **kwargs):
    payment = SupplierPaymentService().create(**_fields(request, json_body(request)))
    return success_response(_presented(payment), status=201)


@guarded
def get_supplier_payment(request, **kwargs):
    record = SupplierPaymentService().get_presented(resource_id(kwargs))
    return success_response(serialize_payment(record))


@guarded
def void_supplier_payment(request, **kwargs):
    payment_id = resource_id(kwargs)
    SupplierPaymentService().void(payment_id, actor_id=actor_id(request))
    return success_response({"id": payment_id, "voided": True})


@guarded
def supplier_payments_for_supplier(request, **kwargs):
    items = SupplierPaymentService().list_for_supplier(resource_id(kwargs, "id", "supplier_id"))
    return success_response({"payments": [serialize_payment(item) for item in items]})


@guarded
def create_supplier_payment_for_supplier(request, **kwargs):
    payment = SupplierPaymentService().create(
        **_fields(
            request,
            json_body(request),
            supplier_id=resource_id(kwargs, "id", "supplier_id"),
        )
    )
    return success_response(_presented(payment), status=201)
