from django.urls import path

from apps.expenses.api import expenses_for_supplier
from apps.finance.api import supplier_balance
from apps.supplier_payments.api import (
    create_supplier_payment_for_supplier,
    supplier_payments_for_supplier,
)
from apps.suppliers import api
from core.access import ALL_ROLES, FINANCE_ROLES, OPERATIONS_ROLES
from core.http import method_view

app_name = "suppliers_api"

urlpatterns = [
    path("", method_view(*ALL_ROLES, GET=api.list_suppliers, POST=api.create_supplier), name="collection"),
    path("services/", method_view(*OPERATIONS_ROLES, GET=api.list_catalog), name="services"),
    path("<str:id>/services/", method_view(*OPERATIONS_ROLES, GET=api.list_offerings, POST=api.create_offering), name="offerings"),
    path(
        "<str:id>/services/<str:service_id>/",
        method_view(*OPERATIONS_ROLES, GET=api.get_offering, PATCH=api.patch_offering),
        name="offering",
    ),
    path("<str:id>/expenses/", method_view(*FINANCE_ROLES, GET=expenses_for_supplier), name="expenses"),
    path(
        "<str:id>/payments/",
        method_view(
            *FINANCE_ROLES,
            GET=supplier_payments_for_supplier,
            POST=create_supplier_payment_for_supplier,
        ),
        name="payments",
    ),
    path("<str:id>/balance/", method_view(*FINANCE_ROLES, GET=supplier_balance), name="balance"),
    path("<str:id>/", method_view(*ALL_ROLES, GET=api.get_supplier, PATCH=api.patch_supplier), name="detail"),
]
