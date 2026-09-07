from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list, name="list"),
    path("new/", views.payment_create, name="create"),
    path("<str:id>/void/", views.payment_void, name="void"),
    path("<str:id>/", views.payment_detail, name="detail"),
]
