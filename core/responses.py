from __future__ import annotations

from typing import Any

from django.http import JsonResponse

from core.exceptions import TourOpsError


def success_response(data: Any = None, *, status: int = 200) -> JsonResponse:
    return JsonResponse({"success": True, "data": {} if data is None else data}, status=status)


def error_response(
    code: str,
    message: str,
    *,
    status: int = 400,
    extra: dict | None = None,
) -> JsonResponse:
    payload: dict[str, Any] = {"code": code, "message": message}
    if extra:
        payload.update(extra)
    return JsonResponse({"success": False, "error": payload}, status=status)


def not_implemented(message: str = "This endpoint is not implemented yet.") -> JsonResponse:
    return error_response("NOT_IMPLEMENTED", message, status=501)


def from_exception(exc: Exception) -> JsonResponse:
    if isinstance(exc, TourOpsError):
        return error_response(exc.code, exc.message, status=exc.http_status)
    return error_response("INTERNAL_ERROR", "An unexpected error occurred.", status=500)


def not_implemented_view(request, *args, **kwargs):
    feature = kwargs.get("feature") or request.path
    return not_implemented(
        f"API endpoint {request.method} {request.path} is not implemented yet. "
        f"See the README URL contracts. Feature: {feature}"
    )
