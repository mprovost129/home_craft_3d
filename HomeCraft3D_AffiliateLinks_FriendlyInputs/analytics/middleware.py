from __future__ import annotations

import hashlib
import uuid
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import AnalyticsEvent


_DEFAULT_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/media/",
    "/__debug__/",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap",
)

# Admin/dashboard paths are optionally excluded via SiteConfig.analytics_exclude_admin_paths
_DEFAULT_ADMIN_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/dashboard/",
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


def _should_exclude_path(path: str, extra_prefixes: Iterable[str], exclude_admin_paths: bool) -> bool:
    for p in _DEFAULT_EXCLUDE_PREFIXES:
        if path.startswith(p):
            return True
    if exclude_admin_paths:
        for p in _DEFAULT_ADMIN_EXCLUDE_PREFIXES:
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


def _normalize_host(host: str) -> str:
    host = (host or "").strip().lower()
    if not host:
        return ""
    # drop port for consistent reporting
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _get_or_create_visitor_id(request) -> str:
    vid = (request.COOKIES.get("hc_vid") or "").strip()
    if len(vid) >= 8:
        return vid[:36]
    return str(uuid.uuid4())


def _get_or_rotate_session_id(request, now: timezone.datetime, inactivity_seconds: int) -> tuple[str, int]:
    sid = (request.COOKIES.get("hc_sid") or "").strip()
    last_ts_raw = (request.COOKIES.get("hc_slt") or "").strip()

    last_ts = 0
    try:
        last_ts = int(last_ts_raw or "0")
    except Exception:
        last_ts = 0

    now_ts = int(now.timestamp())

    # rotate if missing or too old
    if not sid or (last_ts and (now_ts - last_ts) > int(inactivity_seconds or 1800)):
        sid = str(uuid.uuid4())

    return sid[:36], now_ts


class RequestAnalyticsMiddleware:
    """Lightweight first-party server-side analytics (pageviews).

    v2 hardening:
    - Stable visitor id cookie (hc_vid) for unique visitors
    - Session id cookie (hc_sid) with inactivity-based rotation (default 30m)
    - Host/environment captured for stream separation (dev vs prod)
    - Optional exclusions via SiteConfig (exclude staff, exclude admin/dashboard paths)
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

            exclude_admin_paths = bool(getattr(cfg, "analytics_exclude_admin_paths", True)) if cfg else True
            extra_excludes = getattr(settings, "ANALYTICS_EXCLUDE_PATH_PREFIXES", ()) or ()
            if _should_exclude_path(path, extra_excludes, exclude_admin_paths=exclude_admin_paths):
                return response

            ua = request.META.get("HTTP_USER_AGENT", "") or ""
            is_bot = _looks_like_bot(ua)
            if is_bot:
                return response

            user = getattr(request, "user", None)
            is_staff = bool(getattr(user, "is_staff", False)) if user and getattr(user, "is_authenticated", False) else False

            if cfg and bool(getattr(cfg, "analytics_exclude_staff", True)) and is_staff:
                return response

            now = timezone.now()

            vid = _get_or_create_visitor_id(request)
            inactivity_seconds = int(getattr(settings, "ANALYTICS_SESSION_INACTIVITY_SECONDS", 1800) or 1800)
            sid, now_ts = _get_or_rotate_session_id(request, now, inactivity_seconds)

            # throttle per visitor+path to avoid rapid refresh duplicates
            throttle_seconds = int(getattr(settings, "ANALYTICS_THROTTLE_SECONDS", 30) or 30)
            cache_key = f"hc3d:pv:{vid}:{path}"
            if cache.get(cache_key):
                # still set/update cookies even if we skip storing an event
                response.set_cookie("hc_vid", vid, max_age=31536000, samesite="Lax", secure=not settings.DEBUG)
                response.set_cookie("hc_sid", sid, max_age=31536000, samesite="Lax", secure=not settings.DEBUG)
                response.set_cookie("hc_slt", str(now_ts), max_age=31536000, samesite="Lax", secure=not settings.DEBUG)
                return response
            cache.set(cache_key, 1, throttle_seconds)

            ip = _get_client_ip(request)
            ip_hash = _hash_ip(ip)

            session_key = getattr(getattr(request, "session", None), "session_key", "") or ""
            ref = request.META.get("HTTP_REFERER", "") or ""

            host = _normalize_host(request.get_host() or "")
            env = (getattr(settings, "ENVIRONMENT", "") or "").strip() or ("development" if settings.DEBUG else "production")

            AnalyticsEvent.objects.create(
                event_type=AnalyticsEvent.EventType.PAGEVIEW,
                path=path[:512],
                method=method[:8],
                status_code=int(response.status_code),
                visitor_id=vid[:36],
                session_id=sid[:36],
                user=user if user and user.is_authenticated else None,
                session_key=(session_key or "")[:64],
                ip_hash=(ip_hash or "")[:64],
                host=host[:255],
                environment=env[:32],
                is_staff=is_staff,
                is_bot=is_bot,
                user_agent=ua[:400],
                referrer=ref[:512],
                meta={
                    "ts": now.isoformat(),
                },
            )

            # set cookies after logging
            response.set_cookie("hc_vid", vid, max_age=31536000, samesite="Lax", secure=not settings.DEBUG)
            response.set_cookie("hc_sid", sid, max_age=31536000, samesite="Lax", secure=not settings.DEBUG)
            response.set_cookie("hc_slt", str(now_ts), max_age=31536000, samesite="Lax", secure=not settings.DEBUG)

        except Exception:
            return response

        return response
