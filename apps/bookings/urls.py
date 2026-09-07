from django.urls import path

from apps.bookings import views

app_name = "bookings"

urlpatterns = [
    path("", views.booking_list, name="list"),
    path("create/", views.booking_create, name="create"),
    path("<str:id>/confirm/", views.booking_confirm, name="confirm"),
    path("<str:id>/complete/", views.booking_complete, name="complete"),
    path("<str:id>/cancel/", views.booking_cancel, name="cancel"),
    path("<str:id>/invoice/", views.booking_invoice, name="invoice"),
    path("<str:id>/pay/", views.booking_pay, name="pay"),
    path("<str:id>/", views.booking_detail, name="detail"),
]
