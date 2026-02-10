# core/throttle.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Tuple

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse


@dataclass(frozen=True)
class ThrottleRule:
    key_prefix: str
    limit: int
    window_seconds: int


def _get_client_ip(request: HttpRequest) -> str:
    """
    Best-effort client IP.

    If THROTTLE_TRUST_PROXY_HEADERS=True (prod behind your own proxy),
    we trust X-Forwarded-For / X-Real-IP. Otherwise use REMOTE_ADDR.
    """
    trust_proxy = bool(getattr(settings, "THROTTLE_TRUST_PROXY_HEADERS", False))

    if trust_proxy:
        xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            ip = xff.split(",")[0].strip()
            if ip:
                return ip

        xri = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if xri:
            return xri

    return (request.META.get("REMOTE_ADDR") or "ip-unknown").strip() or "ip-unknown"


def _client_fingerprint(request: HttpRequest) -> str:
    """
    Fingerprint is stable enough to throttle abuse, but not overly unique.

    Includes:
    - client ip
    - short user agent prefix
    - user id if authenticated
    """
    ip = _get_client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:60]
    user_part = f"user:{request.user.id}" if getattr(request.user, "is_authenticated", False) else "anon"
    return f"{ip}|{ua}|{user_part}"


def throttle(rule: ThrottleRule, *, methods: Iterable[str] | None = None) -> Callable:
    """
    Cache-based throttle.

    Intended for endpoints that can be abused:
    - Auth (login/register)
    - Q&A create/reply/report/delete
    - cart mutation
    - checkout start
    - download endpoints (GET)  <-- pass methods=("GET",)
    - refund create/trigger
    """
    allowed: Tuple[str, ...] = tuple((m.upper() for m in methods)) if methods else ("POST", "PUT", "PATCH", "DELETE")

    def decorator(view_func: Callable) -> Callable:
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.method.upper() not in allowed:
                return view_func(request, *args, **kwargs)

            fp = _client_fingerprint(request)
            bucket = int(time.time() // max(1, rule.window_seconds))
            cache_key = f"throttle:{rule.key_prefix}:{bucket}:{fp}"

            current = int(cache.get(cache_key, 0) or 0)
            if current >= rule.limit:
                retry_after = max(1, int(rule.window_seconds - (time.time() % max(1, rule.window_seconds))))

                # For typical browser flows, redirect back and show a friendly message when possible.
                try:
                    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
                    referer = (request.META.get("HTTP_REFERER") or "").strip()
                    if "text/html" in accept and referer and request.method.upper() != "GET":
                        try:
                            from django.contrib import messages

                            messages.error(request, "Too many requests. Please try again in a moment.")
                        except Exception:
                            pass
                        from django.shortcuts import redirect

                        return redirect(referer)
                except Exception:
                    pass

                resp = HttpResponse("Too many requests. Please try again shortly.", status=429)
                resp["Retry-After"] = str(retry_after)
                return resp

            cache.set(cache_key, current + 1, timeout=rule.window_seconds + 5)
            return view_func(request, *args, **kwargs)

        wrapped.__name__ = getattr(view_func, "__name__", "wrapped")
        wrapped.__doc__ = getattr(view_func, "__doc__", "")
        wrapped.__module__ = getattr(view_func, "__module__", "")
        return wrapped

    return decorator
