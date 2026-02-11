from __future__ import annotations

import hashlib
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import AnalyticsEvent


_DEFAULT_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/static/",
    "/media/",
    "/__debug__/",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap",
)

_BOT_SUBSTRINGS: tuple[str, ...] = (
    "bot",
    "spider",
    "crawl",
    "slurp",
    "facebookexternalhit",
    "whatsapp",
    "telegrambot",
    "discordbot",
    "twitterbot",
)


def _get_client_ip(request) -> str:
    # Prefer X-Forwarded-For if present (Render / reverse proxy)
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _hash_ip(ip: str) -> str:
    if not ip:
        return ""
    salt = getattr(settings, "ANALYTICS_IP_SALT", "") or settings.SECRET_KEY
    raw = (salt + "|" + ip).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _is_html_response(response) -> bool:
    ctype = (response.get("Content-Type") or "").lower()
    return ctype.startswith("text/html")


def _should_exclude_path(path: str, extra_prefixes: Iterable[str]) -> bool:
    for p in _DEFAULT_EXCLUDE_PREFIXES:
        if path.startswith(p):
            return True
    for p in extra_prefixes:
        if p and path.startswith(p):
            return True
    return False


def _looks_like_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    if not ua:
        return False
    return any(s in ua for s in _BOT_SUBSTRINGS)


class RequestAnalyticsMiddleware:
    """Lightweight server-side analytics (pageviews).

    Records a single PAGEVIEW event for HTML GET/HEAD responses, throttled per ip_hash+path
    to avoid storing duplicates during rapid refreshes.

    This is intentionally simple for v1:
    - no cookies required
    - no JS required
    - respects site-level enable/disable via settings
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        from core.config import get_site_config

        cfg = get_site_config()
        if cfg and hasattr(cfg, "analytics_enabled") and not bool(getattr(cfg, "analytics_enabled")):
            return response

        if not getattr(settings, "ANALYTICS_ENABLED", True):
            return response

        try:
            method = (request.method or "GET").upper()
            if method not in ("GET", "HEAD"):
                return response

            if response.status_code >= 400:
                return response

            if not _is_html_response(response):
                return response

            path = request.path or "/"
            extra_excludes = getattr(settings, "ANALYTICS_EXCLUDE_PATH_PREFIXES", ()) or ()
            if _should_exclude_path(path, extra_excludes):
                return response

            ua = request.META.get("HTTP_USER_AGENT", "") or ""
            if _looks_like_bot(ua):
                return response

            ip = _get_client_ip(request)
            ip_hash = _hash_ip(ip)

            # throttle per ip_hash + path
            throttle_seconds = int(getattr(settings, "ANALYTICS_THROTTLE_SECONDS", 60) or 60)
            cache_key = f"hc3d:pv:{ip_hash}:{path}"
            if cache.get(cache_key):
                return response
            cache.set(cache_key, 1, throttle_seconds)

            session_key = getattr(getattr(request, "session", None), "session_key", "") or ""
            ref = request.META.get("HTTP_REFERER", "") or ""

            AnalyticsEvent.objects.create(
                event_type=AnalyticsEvent.EventType.PAGEVIEW,
                path=path[:512],
                method=method[:8],
                status_code=int(response.status_code),
                user=getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else None,
                session_key=(session_key or "")[:64],
                ip_hash=(ip_hash or "")[:64],
                user_agent=ua[:400],
                referrer=ref[:512],
                meta={
                    "ts": timezone.now().isoformat(),
                },
            )
        except Exception:
            # never break the request path for analytics
            return response

        return response
