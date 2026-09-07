from apps.customers.services import CustomerService, present_customer
from core.http import actor_id, guarded, json_body, resource_id
from core.responses import success_response


@guarded
def list_customers(request, **kwargs):
    return success_response({"customers": CustomerService().list_presented()})


@guarded
def create_customer(request, **kwargs):
    payload = json_body(request)
    customer = CustomerService().create(actor_id=actor_id(request), **payload)
    return success_response(present_customer(customer), status=201)


@guarded
def get_customer(request, **kwargs):
    return success_response(CustomerService().get_presented(resource_id(kwargs)))


@guarded
def patch_customer(request, **kwargs):
    return success_response(CustomerService().get_presented(resource_id(kwargs)))
