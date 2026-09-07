from __future__ import annotations

from functools import wraps
from typing import Callable

from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from core.constants import UserRole
from core.responses import error_response


def get_session_user(request: HttpRequest) -> dict | None:
    """Compatibility adapter: staff identity as a dict keyed by Mongo actor id."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return {
        "id": user.actor_id,
        "pk": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
    }


def clear_session_user(request: HttpRequest) -> None:
    logout(request)


def is_authenticated(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


def safe_next_url(request: HttpRequest, candidate: str | None) -> str | None:
    if not candidate:
        return None
    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None


def _wants_json(request: HttpRequest) -> bool:
    return request.path.startswith("/api/") or "application/json" in request.headers.get(
        "Accept", ""
    )


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not is_authenticated(request):
            if _wants_json(request):
                return error_response("UNAUTHENTICATED", "Login required.", status=401)
            login_url = reverse("accounts:login")
            return redirect(f"{login_url}?next={request.path}")
        return view(request, *args, **kwargs)

    return wrapper


def role_required(*roles: str) -> Callable:
    allowed = {getattr(role, "value", role) for role in roles}

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @login_required
        def wrapper(request: HttpRequest, *args, **kwargs):
            if not request.user.has_role(*allowed):
                if _wants_json(request):
                    return error_response(
                        "PERMISSION_DENIED",
                        "You do not have permission to access this resource.",
                        status=403,
                    )
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def owner_required(view: Callable) -> Callable:
    return role_required(UserRole.OWNER_ADMIN)(view)


def staff_required(view: Callable) -> Callable:
    return role_required(
        UserRole.TRAVEL_AGENT,
        UserRole.ACCOUNTANT,
        UserRole.OWNER_ADMIN,
    )(view)
