from django.urls import path

from apps.finance import api
from core.access import FINANCE_ROLES
from core.http import method_view

app_name = "finance_api"

urlpatterns = [
    path("receivables/", method_view(*FINANCE_ROLES, GET=api.receivables), name="receivables"),
    path("payables/", method_view(*FINANCE_ROLES, GET=api.payables), name="payables"),
    path("customer-balances/", method_view(*FINANCE_ROLES, GET=api.customer_balances), name="customer_balances"),
    path("supplier-balances/", method_view(*FINANCE_ROLES, GET=api.supplier_balances), name="supplier_balances"),
]
