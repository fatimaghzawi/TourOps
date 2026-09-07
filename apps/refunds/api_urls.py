from django.urls import path

from apps.refunds import api
from core.access import FINANCE_ROLES, OWNER_ROLES
from core.http import method_view

app_name = "refunds_api"

urlpatterns = [
    path("", method_view(*FINANCE_ROLES, GET=api.list_refunds, POST=api.create_refund), name="collection"),
    path("<str:id>/approve/", method_view(*OWNER_ROLES, POST=api.approve_refund), name="approve"),
    path("<str:id>/reject/", method_view(*OWNER_ROLES, POST=api.reject_refund), name="reject"),
    path("<str:id>/complete/", method_view(*OWNER_ROLES, POST=api.complete_refund), name="complete"),
    path("<str:id>/", method_view(*FINANCE_ROLES, GET=api.get_refund), name="detail"),
]
