from django.urls import path

from apps.supplier_reservations import api
from core.access import OPERATIONS_ROLES
from core.http import method_view

app_name = "supplier_reservations_api"

urlpatterns = [
    path("", method_view(*OPERATIONS_ROLES, GET=api.list_reservations, POST=api.create_reservation), name="collection"),
    path("<str:id>/confirm/", method_view(*OPERATIONS_ROLES, POST=api.confirm_reservation), name="confirm"),
    path("<str:id>/cancel/", method_view(*OPERATIONS_ROLES, POST=api.cancel_reservation), name="cancel"),
    path("<str:id>/", method_view(*OPERATIONS_ROLES, GET=api.get_reservation, PATCH=api.patch_reservation), name="detail"),
]
