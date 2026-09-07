from django.contrib.auth import logout

from core.access import ALL_ROLES, role_values


class SessionIntegrityMiddleware:
    """Drop authenticated sessions whose role is no longer a known staff role."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._allowed_roles = role_values(*ALL_ROLES)

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            if not getattr(user, "is_active", False):
                logout(request)
            elif getattr(user, "role", None) not in self._allowed_roles:
                logout(request)
        return self.get_response(request)
