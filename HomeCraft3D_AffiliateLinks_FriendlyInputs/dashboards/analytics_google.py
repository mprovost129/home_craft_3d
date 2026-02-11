# dashboards/analytics_google.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings


@dataclass(frozen=True)
class GASummary:
    active_users: int = 0
    screen_page_views: int = 0
    sessions: int = 0
    bounce_rate: float = 0.0
    avg_session_duration_seconds: float = 0.0


def is_configured() -> bool:
    return bool(
        (getattr(settings, "GA4_PROPERTY_ID", "") or "").strip()
        and (
            (getattr(settings, "GA4_CREDENTIALS_JSON", "") or "").strip()
            or (getattr(settings, "GA4_CREDENTIALS_FILE", "") or "").strip()
            or (getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()
        )
    )


def _client():
    """Return a GA4 Data API client, or raise ImportError/ValueError."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "Google Analytics Data API client not installed. Install 'google-analytics-data' and 'google-auth'."
        ) from e

    creds_json = (getattr(settings, "GA4_CREDENTIALS_JSON", "") or "").strip()
    creds_file = (getattr(settings, "GA4_CREDENTIALS_FILE", "") or "").strip()
    if creds_json:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        return BetaAnalyticsDataClient(credentials=creds)
    if creds_file:
        creds = service_account.Credentials.from_service_account_file(creds_file)
        return BetaAnalyticsDataClient(credentials=creds)

    # Fallback to GOOGLE_APPLICATION_CREDENTIALS default behavior if present
    return BetaAnalyticsDataClient()


def _property_path() -> str:
    prop = (getattr(settings, "GA4_PROPERTY_ID", "") or "").strip()
    return f"properties/{prop}"


def get_summary(days: int = 30) -> Dict[str, Any]:
    """Return a dict compatible with the old Plausible summary consumer."""
    if not is_configured():
        return {}

    try:
        from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest  # type: ignore
    except Exception:
        # Will be handled by _client import error below
        pass

    client = _client()

    req = RunReportRequest(
        property=_property_path(),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        metrics=[
            Metric(name="activeUsers"),
            Metric(name="screenPageViews"),
            Metric(name="sessions"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
        ],
    )
    resp = client.run_report(req)
    if not resp.rows:
        return {}

    row = resp.rows[0]
    vals = [v.value for v in row.metric_values]
    try:
        active_users = int(float(vals[0] or 0))
        pageviews = int(float(vals[1] or 0))
        sessions = int(float(vals[2] or 0))
        bounce_rate = float(vals[3] or 0.0)
        avg_dur = float(vals[4] or 0.0)
    except Exception:
        return {}

    # Normalize to keys used in your dashboard UI
    return {
        "visitors": active_users,
        "pageviews": pageviews,
        "visits": sessions,
        "bounce_rate": bounce_rate,
        "visit_duration": avg_dur,
    }


def get_top_pages(days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
    if not is_configured():
        return []

    try:
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest  # type: ignore
    except Exception:
        pass

    client = _client()
    req = RunReportRequest(
        property=_property_path(),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers")],
        limit=limit,
        order_bys=[],
    )
    resp = client.run_report(req)
    results: List[Dict[str, Any]] = []
    for row in resp.rows or []:
        path = row.dimension_values[0].value if row.dimension_values else ""
        mv = row.metric_values or []
        pageviews = int(float(mv[0].value or 0)) if len(mv) > 0 else 0
        visitors = int(float(mv[1].value or 0)) if len(mv) > 1 else 0
        results.append({"page": path, "pageviews": pageviews, "visitors": visitors})
    return results
