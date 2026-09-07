from django.urls import path

from apps.bookings import api
from apps.invoices.api import create_invoice_for_booking
from core.access import FINANCE_ROLES, OPERATIONS_ROLES
from core.http import method_view

app_name = "bookings_api"

urlpatterns = [
    path("", method_view(*OPERATIONS_ROLES, GET=api.list_bookings, POST=api.create_booking), name="collection"),
    path("<str:id>/confirm/", method_view(*OPERATIONS_ROLES, POST=api.confirm_booking), name="confirm"),
    path("<str:id>/complete/", method_view(*OPERATIONS_ROLES, POST=api.complete_booking), name="complete"),
    path("<str:id>/cancel/", method_view(*OPERATIONS_ROLES, POST=api.cancel_booking), name="cancel"),
    path("<str:booking_id>/invoice/", method_view(*FINANCE_ROLES, POST=create_invoice_for_booking), name="invoice"),
    path("<str:id>/", method_view(*OPERATIONS_ROLES, GET=api.get_booking, PATCH=api.patch_booking), name="detail"),
]
