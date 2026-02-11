from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Count
from django.utils import timezone

from analytics.models import AnalyticsEvent


def is_configured() -> bool:
    # Native analytics is always available if the app is installed.
    return True


def _normalize_range(
    *,
    start: Optional[timezone.datetime] = None,
    end: Optional[timezone.datetime] = None,
    days: int = 30,
) -> Tuple[timezone.datetime, Optional[timezone.datetime]]:
    """
    Normalize a time range.

    - If start is not provided, default to now - days.
    - If end is provided, it is treated as an exclusive upper bound.
    """
    now = timezone.now()
    if start is None:
        start = now - timezone.timedelta(days=int(days or 30))
    if end is not None and timezone.is_naive(end):
        end = timezone.make_aware(end, timezone.get_current_timezone())
    if timezone.is_naive(start):
        start = timezone.make_aware(start, timezone.get_current_timezone())
    return start, end


def get_summary(*, days: int = 30, start: Optional[timezone.datetime] = None, end: Optional[timezone.datetime] = None) -> Dict[str, Any]:
    start_dt, end_dt = _normalize_range(start=start, end=end, days=days)

    qs = AnalyticsEvent.objects.filter(
        event_type=AnalyticsEvent.EventType.PAGEVIEW,
        created_at__gte=start_dt,
    )
    if end_dt is not None:
        qs = qs.filter(created_at__lt=end_dt)

    pageviews = qs.count()
    visitors = qs.values("ip_hash").exclude(ip_hash="").distinct().count()
    sessions = qs.values("session_key").exclude(session_key="").distinct().count()

    return {
        "pageviews": pageviews,
        "visitors": visitors,
        "visits": sessions,
    }


def get_top_pages(
    *,
    days: int = 30,
    start: Optional[timezone.datetime] = None,
    end: Optional[timezone.datetime] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = _normalize_range(start=start, end=end, days=days)

    qs = AnalyticsEvent.objects.filter(
        event_type=AnalyticsEvent.EventType.PAGEVIEW,
        created_at__gte=start_dt,
    )
    if end_dt is not None:
        qs = qs.filter(created_at__lt=end_dt)

    qs = (
        qs.values("path")
        .annotate(pageviews=Count("id"), visitors=Count("ip_hash", distinct=True))
        .order_by("-pageviews")[: int(limit or 10)]
    )

    rows: List[Dict[str, Any]] = []
    for r in qs:
        rows.append({"page": r["path"], "pageviews": r["pageviews"], "visitors": r["visitors"]})
    return rows


def get_throttle_summary(
    *,
    days: int = 7,
    start: Optional[timezone.datetime] = None,
    end: Optional[timezone.datetime] = None,
) -> Dict[str, Any]:
    start_dt, end_dt = _normalize_range(start=start, end=end, days=days)

    qs = AnalyticsEvent.objects.filter(
        event_type=getattr(AnalyticsEvent.EventType, "THROTTLE", "THROTTLE"),
        created_at__gte=start_dt,
    )
    if end_dt is not None:
        qs = qs.filter(created_at__lt=end_dt)

    throttles = qs.count()
    visitors = qs.values("ip_hash").exclude(ip_hash="").distinct().count()
    users = qs.values("user_id").exclude(user_id=None).distinct().count()

    return {
        "throttles": throttles,
        "visitors": visitors,
        "users": users,
    }


def get_top_throttle_rules(
    *,
    days: int = 7,
    start: Optional[timezone.datetime] = None,
    end: Optional[timezone.datetime] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = _normalize_range(start=start, end=end, days=days)

    qs = AnalyticsEvent.objects.filter(
        event_type=getattr(AnalyticsEvent.EventType, "THROTTLE", "THROTTLE"),
        created_at__gte=start_dt,
    )
    if end_dt is not None:
        qs = qs.filter(created_at__lt=end_dt)

    # meta["rule"] stores key_prefix
    qs = qs.values("meta__rule").annotate(count=Count("id")).order_by("-count")[: int(limit or 8)]

    rows: List[Dict[str, Any]] = []
    for r in qs:
        rows.append({"rule": r.get("meta__rule") or "unknown", "count": r.get("count") or 0})
    return rows
