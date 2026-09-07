from apps.bookings.services import BookingService
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.money import to_money
from core.responses import success_response


def _presented(booking) -> dict:
    payload = BookingService().get_presented(booking["_id"])
    payload["total"] = str(to_money(payload.get("total")))
    payload["created_at"] = payload["created_at"].isoformat() if hasattr(payload.get("created_at"), "isoformat") else payload.get("created_at")
    payload["updated_at"] = payload["updated_at"].isoformat() if hasattr(payload.get("updated_at"), "isoformat") else payload.get("updated_at")
    return payload


@guarded
def list_bookings(request, **kwargs):
    items = BookingService().list_presented(
        tour_id=query_value(request, "tour_id"),
        customer_id=query_value(request, "customer_id"),
        status=query_value(request, "status"),
    )
    return success_response({"bookings": items})


@guarded
def create_booking(request, **kwargs):
    payload = json_body(request)
    booking = BookingService().create(
        actor_id=actor_id(request),
        customer_id=payload.get("customer_id"),
        tour_id=payload.get("tour_id"),
        travelers=payload.get("travelers"),
        notes=payload.get("notes"),
    )
    return success_response(_presented(booking), status=201)


@guarded
def get_booking(request, **kwargs):
    return success_response(BookingService().get_presented(resource_id(kwargs)))


@guarded
def patch_booking(request, **kwargs):
    return success_response(BookingService().get_presented(resource_id(kwargs)))


@guarded
def confirm_booking(request, **kwargs):
    booking = BookingService().confirm(resource_id(kwargs), actor_id=actor_id(request))
    return success_response(_presented(booking))


@guarded
def complete_booking(request, **kwargs):
    booking = BookingService().complete(resource_id(kwargs), actor_id=actor_id(request))
    return success_response(_presented(booking))


@guarded
def cancel_booking(request, **kwargs):
    booking = BookingService().cancel(resource_id(kwargs), actor_id=actor_id(request))
    return success_response(_presented(booking))
