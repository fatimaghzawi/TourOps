from django.conf import settings


class DebugAllowSameOriginFramesMiddleware:
    """Presentation iframes the live product. Only when DEBUG: allow same-origin framing."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response
