from django.urls import path

from apps.packages import api
from core.access import OPERATIONS_ROLES
from core.http import method_view

app_name = "packages_api"

urlpatterns = [
    path("", method_view(*OPERATIONS_ROLES, GET=api.list_packages, POST=api.create_package), name="collection"),
    path("<str:id>/tours/", method_view(*OPERATIONS_ROLES, GET=api.tours_for_package), name="tours"),
    path("<str:id>/", method_view(*OPERATIONS_ROLES, GET=api.get_package, PATCH=api.patch_package), name="detail"),
]
