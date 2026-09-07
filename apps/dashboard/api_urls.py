from django.urls import path

from apps.dashboard import api
from core.access import FINANCE_ROLES, OPERATIONS_ROLES, OWNER_ROLES
from core.http import method_view, unimplemented

app_name = "dashboard_api"

urlpatterns = [
    path(
        "agent/",
        unimplemented(
            "GET",
            message="GET /api/dashboard/agent/ is not implemented yet. Owner: Dev 1.",
            roles=OPERATIONS_ROLES,
        ),
        name="agent",
    ),
    path("accountant/", method_view(*FINANCE_ROLES, GET=api.accountant), name="accountant"),
    path("owner/", method_view(*OWNER_ROLES, GET=api.owner), name="owner"),
]
