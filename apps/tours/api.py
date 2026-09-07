from apps.tours.services import TourService, serialize_tour
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _presented(tour) -> dict:
    return serialize_tour(TourService().get_presented(tour["_id"]))


@guarded
def list_tours(request, **kwargs):
    items = TourService().list_presented(
        status=query_value(request, "status"),
        package_id=query_value(request, "package_id"),
    )
    return success_response({"tours": [serialize_tour(item) for item in items]})


@guarded
def create_tour(request, **kwargs):
    payload = json_body(request)
    tour = TourService().create(actor_id=actor_id(request), **payload)
    return success_response(_presented(tour), status=201)


@guarded
def get_tour(request, **kwargs):
    record = TourService().get_presented(resource_id(kwargs))
    return success_response(serialize_tour(record))


@guarded
def patch_tour(request, **kwargs):
    payload = json_body(request)
    tour = TourService().update(
        resource_id(kwargs),
        actor_id=actor_id(request),
        **payload,
    )
    return success_response(_presented(tour))


@guarded
def tour_availability(request, **kwargs):
    record = TourService().get_presented(resource_id(kwargs), include_extras=False)
    return success_response(
        {
            "id": record["id"],
            "code": record["code"],
            "name": record["name"],
            "capacity": record["capacity"],
            "booked": record["booked"],
            "available": record["available"],
            "pct": record["pct"],
            "status": record["status"],
            "dates": record["dates"],
        }
    )
