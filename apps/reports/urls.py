from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("profitability/", views.tour_profitability, name="profitability"),
    path("revenue/", views.report_revenue, name="revenue"),
    path("expenses/", views.report_expenses, name="expenses"),
    path("profit-loss/", views.report_profit_loss, name="profit_loss"),
    path("payments/", views.report_payments, name="payments"),
    path("refunds/", views.report_refunds, name="refunds"),
    path("transactions/", views.report_transactions, name="transactions"),
]
