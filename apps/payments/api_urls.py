from django.urls import path

from apps.payments import api
from apps.receipts.api import receipt_for_payment
from apps.refunds.api import refund_from_payment
from core.access import FINANCE_ROLES
from core.http import method_view

app_name = "payments_api"

urlpatterns = [
    path("", method_view(*FINANCE_ROLES, GET=api.list_payments, POST=api.create_payment), name="collection"),
    path("<str:id>/receipt/", method_view(*FINANCE_ROLES, GET=receipt_for_payment), name="receipt"),
    path("<str:id>/refund/", method_view(*FINANCE_ROLES, POST=refund_from_payment), name="refund"),
    path("<str:id>/void/", method_view(*FINANCE_ROLES, POST=api.void_payment), name="void"),
    path("<str:id>/", method_view(*FINANCE_ROLES, GET=api.get_payment), name="detail"),
]
