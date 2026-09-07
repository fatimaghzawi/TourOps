from django.urls import path

from apps.invoices import views

app_name = "invoices"

urlpatterns = [
    path("", views.invoice_list, name="list"),
    path("new/", views.invoice_create, name="create"),
    path("from-booking/<str:booking_id>/", views.invoice_from_booking, name="from_booking"),
    path("<str:id>/reissue/", views.invoice_reissue, name="reissue"),
    path("<str:id>/print/", views.invoice_print, name="print"),
    path("<str:id>/pay/", views.invoice_pay, name="pay"),
    path("<str:id>/cancel/", views.invoice_cancel, name="cancel"),
    path("<str:id>/", views.invoice_detail, name="detail"),
]
