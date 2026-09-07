from django.urls import path

from apps.suppliers import views

app_name = "suppliers"

urlpatterns = [
    path("", views.supplier_list, name="list"),
    path("create/", views.supplier_create, name="create"),
    path("hotels/", views.hotels, name="hotels"),
    path("transportation/", views.transportation, name="transportation"),
    path("tour-guides/", views.tour_guides, name="tour_guides"),
    path("other/", views.other_suppliers, name="other"),
    path("services/", views.catalog_index, name="services"),
    path("services/new/", views.offering_create, name="service_new"),
    path("<str:id>/services/new/", views.offering_create, name="service_create"),
    path("<str:id>/services/<str:service_id>/edit/", views.offering_edit, name="service_edit"),
    path("<str:id>/services/<str:service_id>/status/", views.offering_set_status, name="service_status"),
    path("<str:id>/services/<str:service_id>/delete/", views.offering_delete, name="service_delete"),
    path("<str:id>/edit/", views.supplier_edit, name="edit"),
    path("<str:id>/delete/", views.supplier_delete, name="delete"),
    path("<str:id>/", views.supplier_detail, name="detail"),
]
