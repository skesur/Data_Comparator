import logging
import traceback

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class JsonErrorMiddleware:
    """
    If anything under /api/ raises an unhandled exception, return a
    JSON error body instead of Django's HTML error page. Without this,
    the frontend's `res.json()` call fails with a confusing
    "Unexpected token '<'" — because it just tried to parse an HTML
    error page as JSON.

    In DEBUG mode the JSON body includes the traceback so it's easy
    to see exactly what broke without digging through the runserver
    console.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/"):
            return None  # let Django handle non-API errors normally

        logger.exception("Unhandled exception on %s", request.path)

        payload = {"ok": False, "error": str(exception) or exception.__class__.__name__}
        if settings.DEBUG:
            payload["traceback"] = traceback.format_exc()

        return JsonResponse(payload, status=500)
