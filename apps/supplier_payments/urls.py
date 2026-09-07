from django.urls import path

from apps.supplier_payments import views

app_name = "supplier_payments"

urlpatterns = [
    path("", views.supplier_payment_list, name="list"),
    path("create/", views.supplier_payment_create, name="create"),
    path("<str:id>/void/", views.supplier_payment_void, name="void"),
    path("<str:id>/", views.supplier_payment_detail, name="detail"),
]
