from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.dashboard.services import DashboardService
from apps.supplier_reservations.services import SupplierReservationService
from core.access import dashboard_for_role
from core.constants import UserRole
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import get_session_user, login_required, role_required


def _params(request) -> dict:
    return {
        "month": request.GET.get("month") or "",
        "from": request.GET.get("from") or "",
        "to": request.GET.get("to") or "",
        "tour": request.GET.get("tour") or "",
    }


@login_required
def home(request):
    user = get_session_user(request)
    return redirect(reverse(dashboard_for_role(user["role"])))


@login_required
@role_required(UserRole.TRAVEL_AGENT, UserRole.OWNER_ADMIN)
def agent(request):
    try:
        desk = SupplierReservationService().ops_desk()
    except (DatabaseUnavailableError, TourOpsError):
        desk = {
            "requested": 0,
            "confirmed": 0,
            "upcoming": 0,
            "release_watch": [],
            "awaiting": [],
        }
    return render(
        request,
        "dashboard/agent.html",
        {
            "page_title": "Operations dashboard",
            "page_heading": "Operations command center",
            "desk": desk,
        },
    )


@login_required
@role_required(UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
def accountant(request):
    params = _params(request)
    try:
        dash = DashboardService().accountant(params)
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Dashboard numbers are unavailable.")
        dash = None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        dash = None
    return render(
        request,
        "dashboard/accountant.html",
        {
            "page_title": "Accountant dashboard",
            "page_heading": "Finance command center",
            "filters": params,
            "dash": dash,
        },
    )


@login_required
@role_required(UserRole.OWNER_ADMIN)
def owner(request):
    params = _params(request)
    try:
        dash = DashboardService().owner(params)
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Dashboard numbers are unavailable.")
        dash = None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        dash = None
    try:
        desk = SupplierReservationService().ops_desk()
    except (DatabaseUnavailableError, TourOpsError):
        desk = None
    return render(
        request,
        "dashboard/owner.html",
        {
            "page_title": "Owner dashboard",
            "page_heading": "Owner command center",
            "filters": params,
            "dash": dash,
            "desk": desk,
        },
    )
