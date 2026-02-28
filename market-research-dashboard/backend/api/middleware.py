"""API token middleware — protects /api/ endpoints in production."""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse


class APITokenMiddleware:
    """Require Bearer token for /api/ endpoints when DEBUG=False.

    Exempt paths (e.g. /api/health) are always accessible.
    When API_ACCESS_TOKEN is empty, no enforcement is applied.
    """

    EXEMPT_PATHS = ["/api/health", "/api/health/"]

    def __init__(self, get_response):  # type: ignore[no-untyped-def]
        self.get_response = get_response

    def __call__(self, request):  # type: ignore[no-untyped-def]
        if (
            request.path.startswith("/api/")
            and request.path not in self.EXEMPT_PATHS
            and not settings.DEBUG
        ):
            expected = getattr(settings, "API_ACCESS_TOKEN", "")
            if expected:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token != expected:
                    return JsonResponse({"error": "unauthorized"}, status=401)

        return self.get_response(request)
