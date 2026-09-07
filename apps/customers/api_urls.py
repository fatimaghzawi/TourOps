from django.urls import path

from apps.customers import api
from apps.finance.api import customer_balance
from core.access import FINANCE_ROLES, OPERATIONS_ROLES
from core.http import method_view

app_name = "customers_api"

urlpatterns = [
    path("", method_view(*OPERATIONS_ROLES, GET=api.list_customers, POST=api.create_customer), name="collection"),
    path("<str:id>/balance/", method_view(*FINANCE_ROLES, GET=customer_balance), name="balance"),
    path("<str:id>/", method_view(*OPERATIONS_ROLES, GET=api.get_customer, PATCH=api.patch_customer), name="detail"),
]
