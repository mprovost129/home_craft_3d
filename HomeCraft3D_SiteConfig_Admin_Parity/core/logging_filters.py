# core/logging_filters.py
from __future__ import annotations

import logging

from .logging_context import get_context


class RequestContextFilter(logging.Filter):
    """Inject request context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_context()
        record.request_id = getattr(ctx, "request_id", "-") if ctx else "-"
        record.user_id = getattr(ctx, "user_id", None) if ctx else None
        record.path = getattr(ctx, "path", "") if ctx else ""
        return True
