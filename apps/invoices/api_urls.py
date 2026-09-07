from django.urls import path

from apps.invoices import api
from apps.payments.api import create_payment_for_invoice, payments_for_invoice
from core.access import FINANCE_ROLES
from core.http import method_view

app_name = "invoices_api"

urlpatterns = [
    path("", method_view(*FINANCE_ROLES, GET=api.list_invoices, POST=api.create_invoice), name="collection"),
    path(
        "<str:id>/payments/",
        method_view(*FINANCE_ROLES, GET=payments_for_invoice, POST=create_payment_for_invoice),
        name="payments",
    ),
    path("<str:id>/cancel/", method_view(*FINANCE_ROLES, POST=api.cancel_invoice), name="cancel"),
    path("<str:id>/", method_view(*FINANCE_ROLES, GET=api.get_invoice, PATCH=api.patch_invoice), name="detail"),
]
