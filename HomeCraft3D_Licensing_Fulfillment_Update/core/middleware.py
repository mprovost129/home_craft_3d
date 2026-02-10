# core/middleware.py
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from .logging_context import clear_context, new_request_id, set_context


class RequestIDMiddleware(MiddlewareMixin):
    """
    Adds a stable request id for observability.

    - request.request_id
    - response header: X-Request-ID
    - threadlocal context for logging filters
    """

    header_name = "HTTP_X_REQUEST_ID"
    response_header = "X-Request-ID"

    def process_request(self, request):
        rid = (request.META.get(self.header_name) or "").strip() or new_request_id()
        request.request_id = rid
        user_id = getattr(getattr(request, "user", None), "id", None) if getattr(request, "user", None) and request.user.is_authenticated else None
        set_context(request_id=rid, user_id=user_id, path=(request.path or ""))

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            try:
                response[self.response_header] = rid
            except Exception:
                pass
        clear_context()
        return response

    def process_exception(self, request, exception):
        clear_context()
        return None
