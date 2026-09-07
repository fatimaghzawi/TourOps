from django.urls import path

from apps.reports import api
from core.access import REPORT_ROLES
from core.http import method_view

app_name = "reports_api"

urlpatterns = [
    path("revenue/", method_view(*REPORT_ROLES, GET=api.revenue), name="revenue"),
    path("expenses/", method_view(*REPORT_ROLES, GET=api.expenses), name="expenses"),
    path("payments/", method_view(*REPORT_ROLES, GET=api.payments), name="payments"),
    path("refunds/", method_view(*REPORT_ROLES, GET=api.refunds), name="refunds"),
    path("receivables/", method_view(*REPORT_ROLES, GET=api.receivables), name="receivables"),
    path("payables/", method_view(*REPORT_ROLES, GET=api.payables), name="payables"),
    path("tour-profitability/", method_view(*REPORT_ROLES, GET=api.tour_profitability), name="tour_profitability"),
    path("profit-loss/", method_view(*REPORT_ROLES, GET=api.profit_loss), name="profit_loss"),
    path("transactions/", method_view(*REPORT_ROLES, GET=api.transactions), name="transactions"),
]
