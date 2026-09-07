from django.urls import path

from apps.supplier_reservations import views

app_name = "supplier_reservations"

urlpatterns = [
    path("", views.reservation_list, name="list"),
    path("create/", views.reservation_create, name="create"),
    path("<str:id>/edit/", views.reservation_edit, name="edit"),
    path("<str:id>/confirm/", views.reservation_confirm, name="confirm"),
    path("<str:id>/cancel/", views.reservation_cancel, name="cancel"),
    path("<str:id>/email/", views.reservation_email, name="email"),
    path("<str:id>/", views.reservation_detail, name="detail"),
]
