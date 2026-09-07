from apps.suppliers.offerings import SupplierOfferingService, serialize_offering
from apps.suppliers.services import SupplierService, serialize_supplier
from core.access import OPERATIONS_ROLES
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import error_response, success_response


def _require_ops(request):
    if not request.user.has_role(*OPERATIONS_ROLES):
        return error_response(
            "PERMISSION_DENIED",
            "You do not have permission to access this resource.",
            status=403,
        )
    return None


def _presented(supplier) -> dict:
    return serialize_supplier(SupplierService().get_presented(supplier["_id"]))


@guarded
def list_suppliers(request, **kwargs):
    items = SupplierService().list_presented(
        supplier_type=query_value(request, "supplier_type", "type"),
        group=query_value(request, "group"),
        status=query_value(request, "status"),
    )
    return success_response({"suppliers": [serialize_supplier(item) for item in items]})


@guarded
def create_supplier(request, **kwargs):
    denied = _require_ops(request)
    if denied:
        return denied
    payload = json_body(request)
    supplier = SupplierService().create(
        actor_id=actor_id(request),
        name=payload.get("name") or "",
        supplier_type=payload.get("supplier_type") or payload.get("type") or "",
        **{key: value for key, value in payload.items() if key not in {"name", "supplier_type", "type"}},
    )
    return success_response(_presented(supplier), status=201)


@guarded
def get_supplier(request, **kwargs):
    record = SupplierService().get_presented(resource_id(kwargs))
    return success_response(serialize_supplier(record))


@guarded
def patch_supplier(request, **kwargs):
    denied = _require_ops(request)
    if denied:
        return denied
    payload = json_body(request)
    changes = dict(payload)
    if "type" in changes and "supplier_type" not in changes:
        changes["supplier_type"] = changes.pop("type")
    else:
        changes.pop("type", None)
    supplier = SupplierService().update(
        resource_id(kwargs),
        actor_id=actor_id(request),
        **changes,
    )
    return success_response(_presented(supplier))


@guarded
def list_catalog(request, **kwargs):
    items = SupplierOfferingService().list_catalog(status=query_value(request, "status") or "ACTIVE", q=query_value(request, "q"))
    return success_response({"services": [serialize_offering(item) for item in items]})


@guarded
def list_offerings(request, **kwargs):
    items = SupplierOfferingService().list_for_supplier(resource_id(kwargs), status=query_value(request, "status"))
    return success_response({"services": [serialize_offering(item) for item in items]})


@guarded
def create_offering(request, **kwargs):
    payload = json_body(request)
    offering = SupplierOfferingService().create(
        actor_id=actor_id(request),
        supplier_id=resource_id(kwargs),
        name=payload.get("name") or "",
        service_kind=payload.get("service_kind"),
        estimated_cost=payload.get("estimated_cost"),
        cost_basis=payload.get("cost_basis"),
        currency=payload.get("currency"),
        description=payload.get("description"),
        notes=payload.get("notes"),
    )
    return success_response(serialize_offering(SupplierOfferingService().get_presented(offering["_id"])), status=201)


@guarded
def get_offering(request, **kwargs):
    return success_response(serialize_offering(SupplierOfferingService().get_presented(resource_id(kwargs, "service_id"))))


@guarded
def patch_offering(request, **kwargs):
    payload = json_body(request)
    offering = SupplierOfferingService().update(
        resource_id(kwargs, "service_id"),
        actor_id=actor_id(request),
        **payload,
    )
    return success_response(serialize_offering(SupplierOfferingService().get_presented(offering["_id"])))
