from django.urls import path

from apps.finance import views

app_name = "finance"

urlpatterns = [
    path("customer-balances/", views.customer_balances, name="customer_balances"),
    path("supplier-balances/", views.supplier_balances, name="supplier_balances"),
    path("receivables/", views.receivables, name="receivables"),
    path("payables/", views.payables, name="payables"),
]
