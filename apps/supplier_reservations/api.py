from apps.supplier_reservations.services import SupplierReservationService
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _json_safe(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _presented(document) -> dict:
    return _json_safe(SupplierReservationService().get_presented(document["_id"]))


@guarded
def list_reservations(request, **kwargs):
    items = SupplierReservationService().list_presented(
        tour_id=query_value(request, "tour_id") or kwargs.get("tour_id") or kwargs.get("id"),
        supplier_id=query_value(request, "supplier_id"),
        status=query_value(request, "status"),
    )
    return success_response(_json_safe({"reservations": items}))


@guarded
def create_reservation(request, **kwargs):
    payload = dict(json_body(request))
    payload.pop("room_allocations", None)
    payload.pop("allocations", None)
    if kwargs.get("id") or kwargs.get("tour_id"):
        payload["tour_id"] = kwargs.get("tour_id") or kwargs.get("id")
    reservation = SupplierReservationService().create(actor_id=actor_id(request), **payload)
    return success_response(_presented(reservation), status=201)


@guarded
def get_reservation(request, **kwargs):
    return success_response(_json_safe(SupplierReservationService().get_presented(resource_id(kwargs))))


@guarded
def patch_reservation(request, **kwargs):
    reservation = SupplierReservationService().update(
        resource_id(kwargs),
        actor_id=actor_id(request),
        **json_body(request),
    )
    return success_response(_presented(reservation))


@guarded
def confirm_reservation(request, **kwargs):
    payload = json_body(request)
    reservation = SupplierReservationService().confirm(
        resource_id(kwargs),
        actor_id=actor_id(request),
        confirmation_number=payload.get("confirmation_number") or payload.get("confirmation") or "",
    )
    return success_response(_presented(reservation))


@guarded
def cancel_reservation(request, **kwargs):
    reservation = SupplierReservationService().cancel(resource_id(kwargs), actor_id=actor_id(request))
    return success_response(_presented(reservation))


@guarded
def tour_accommodation(request, **kwargs):
    return success_response(_json_safe(SupplierReservationService().accommodation_snapshot(resource_id(kwargs, "id", "tour_id"))))
