from django.urls import path

from apps.packages import views

app_name = "packages"

urlpatterns = [
    path("", views.package_list, name="list"),
    path("create/", views.package_create, name="create"),
    path("<str:id>/edit/", views.package_edit, name="edit"),
    path("<str:id>/delete/", views.package_delete, name="delete"),
    path("<str:id>/", views.package_detail, name="detail"),
]
