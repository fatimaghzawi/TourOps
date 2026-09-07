from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps

from django.http import HttpRequest

from core.exceptions import TourOpsError, ValidationError
from core.permissions import get_session_user, login_required, role_required
from core.responses import error_response, from_exception, not_implemented


def json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError as extra:
        raise ValidationError("Invalid JSON.") from extra
    if not isinstance(payload, dict):
        raise ValidationError("JSON object required.")
    return payload


def query_value(request: HttpRequest, *names: str, default=None):
    for name in names:
        value = request.GET.get(name)
        if value not in (None, ""):
            return value
    return default


def query_filters(request: HttpRequest) -> dict:
    return {
        "month": query_value(request, "month") or "",
        "from": query_value(request, "from", "date_from") or "",
        "to": query_value(request, "to", "date_to") or "",
        "tour": query_value(request, "tour", "tour_id") or "",
        "tour_id": query_value(request, "tour_id", "tour") or "",
        "supplier_id": query_value(request, "supplier_id") or "",
        "customer_id": query_value(request, "customer_id") or "",
    }


def resource_id(kwargs: dict, *names: str):
    for name in names:
        value = kwargs.get(name)
        if value not in (None, ""):
            return value
    return kwargs.get("id")


def actor_id(request: HttpRequest) -> str:
    return get_session_user(request)["id"]


def actor_role(request: HttpRequest) -> str:
    return get_session_user(request)["role"]


def client_ip(request: HttpRequest) -> str | None:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


def guarded(view: Callable):
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except TourOpsError as extra:
            return from_exception(extra)

    return wrapper


def method_view(*roles, **handlers: Callable):
    allowed = sorted(handlers)

    def view(request: HttpRequest, *args, **kwargs):
        handler = handlers.get(request.method)
        if handler is None:
            return error_response(
                "METHOD_NOT_ALLOWED",
                f"Allowed methods: {', '.join(allowed)}.",
                status=405,
            )
        return handler(request, *args, **kwargs)

    view.handlers = handlers
    return role_required(*roles)(view) if roles else login_required(view)


def unimplemented(*methods: str, message: str | None = None, roles: tuple = ()):
    def handler(request, **kwargs):
        return not_implemented(message or f"{request.method} {request.path} is not implemented yet.")

    return method_view(*roles, **{method: handler for method in methods})
