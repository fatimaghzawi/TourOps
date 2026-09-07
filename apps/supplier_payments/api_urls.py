from django.urls import path

from apps.supplier_payments import api
from core.access import FINANCE_ROLES
from core.http import method_view

app_name = "supplier_payments_api"

urlpatterns = [
    path("", method_view(*FINANCE_ROLES, GET=api.list_supplier_payments, POST=api.create_supplier_payment), name="collection"),
    path("<str:id>/void/", method_view(*FINANCE_ROLES, POST=api.void_supplier_payment), name="void"),
    path("<str:id>/", method_view(*FINANCE_ROLES, GET=api.get_supplier_payment), name="detail"),
]
