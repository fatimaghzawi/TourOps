from apps.packages.services import PackageService, serialize_package
from apps.tours.services import TourService, serialize_tour
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _presented(package) -> dict:
    return serialize_package(PackageService().get_presented(package["_id"]))


@guarded
def list_packages(request, **kwargs):
    items = PackageService().list_presented(status=query_value(request, "status"))
    return success_response({"packages": [serialize_package(item) for item in items]})


@guarded
def create_package(request, **kwargs):
    payload = json_body(request)
    package = PackageService().create(actor_id=actor_id(request), **payload)
    return success_response(_presented(package), status=201)


@guarded
def get_package(request, **kwargs):
    record = PackageService().get_presented(resource_id(kwargs))
    return success_response(serialize_package(record))


@guarded
def patch_package(request, **kwargs):
    payload = json_body(request)
    package = PackageService().update(
        resource_id(kwargs),
        actor_id=actor_id(request),
        **payload,
    )
    return success_response(_presented(package))


@guarded
def tours_for_package(request, **kwargs):
    package_id = resource_id(kwargs)
    PackageService().get(package_id)
    items = TourService().list_presented(package_id=package_id)
    return success_response({"tours": [serialize_tour(item) for item in items]})
