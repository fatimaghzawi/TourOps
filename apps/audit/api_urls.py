from django.urls import path

from apps.audit import api
from core.access import OWNER_ROLES
from core.http import method_view

app_name = "audit_api"

urlpatterns = [
    path("", method_view(*OWNER_ROLES, GET=api.list_audit_logs), name="collection"),
    path("<str:id>/", method_view(*OWNER_ROLES, GET=api.get_audit_log), name="detail"),
]
