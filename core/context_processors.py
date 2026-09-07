from datetime import datetime

from core.access import (
    can_access_finance,
    can_access_operations,
    dashboard_for_role,
    is_owner,
)
from core.constants import UserRole
from core.permissions import get_session_user


BRAND = {
    "name": "TourOps",
    "subtitle": "Travel Agency Operations & Finance",
    "tagline": "From Booking to Balance",
}


def branding(request):
    brand = dict(BRAND)
    brand.update({"legal_name": "", "email": "", "phone": "", "address": ""})
    try:
        from apps.accounts.settings_service import SettingsService

        agency = (SettingsService().get().get("agency") or {})
        if agency.get("name"):
            brand["name"] = agency["name"]
        brand["legal_name"] = agency.get("legal_name") or ""
        brand["email"] = agency.get("email") or ""
        brand["phone"] = agency.get("phone") or ""
        brand["address"] = agency.get("address") or ""
    except Exception:
        pass
    return {"brand": brand}


def current_user(request):
    user = get_session_user(request)
    display_name = ""
    initial = "T"
    if user:
        display_name = " ".join(
            part for part in (user.get("first_name"), user.get("last_name")) if part
        ) or user.get("email") or "User"
        initial = (display_name or "U")[0].upper()
    return {
        "current_user": user,
        "current_user_name": display_name,
        "current_user_initial": initial,
        "current_role": user.get("role") if user else None,
        "UserRole": UserRole,
    }


def navigation(request):
    user = get_session_user(request)
    role = user.get("role") if user else None
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    first = (user or {}).get("first_name") or ""
    return {
        "nav": {
            "is_agent": role == UserRole.TRAVEL_AGENT,
            "is_accountant": role == UserRole.ACCOUNTANT,
            "is_owner": is_owner(request),
            "ops": can_access_operations(request),
            "finance": can_access_finance(request),
            "system": is_owner(request),
            "role": role,
            "dashboard": dashboard_for_role(role) if role else "dashboard:home",
        },
        "greeting": greeting,
        "greeting_name": first or "there",
        "unread_count": _unread_count(user),
        "nav_notifications": _nav_notifications(user),
        "today_label": datetime.now().strftime("%A, %d %B %Y"),
    }


def _notification_service():
    from apps.notifications.services import NotificationService

    return NotificationService()


def _unread_count(user) -> int:
    if not user:
        return 0
    try:
        return _notification_service().unread_count(user["id"])
    except Exception:
        return 0


def _nav_notifications(user) -> list:
    if not user:
        return []
    try:
        return _notification_service().list_for_user(user["id"], limit=6)
    except Exception:
        return []
