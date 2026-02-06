from __future__ import annotations

from typing import Any, Dict, List

import requests
from django.conf import settings

BASE_URL = "https://plausible.io/api/v1/stats"


def is_configured() -> bool:
	return bool(settings.PLAUSIBLE_API_KEY and settings.PLAUSIBLE_SITE_ID)


def _headers() -> Dict[str, str]:
	return {"Authorization": f"Bearer {settings.PLAUSIBLE_API_KEY}"}


def _get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
	url = f"{BASE_URL}/{path.lstrip('/')}"
	response = requests.get(url, headers=_headers(), params=params, timeout=10)
	response.raise_for_status()
	return response.json()


def get_summary(period: str = "30d") -> Dict[str, Any]:
	if not is_configured():
		return {}

	params = {
		"site_id": settings.PLAUSIBLE_SITE_ID,
		"period": period,
		"metrics": "visitors,pageviews,visits,bounce_rate,visit_duration",
	}
	data = _get("aggregate", params)
	return data.get("results", {}) or {}


def get_top_pages(period: str = "30d", limit: int = 10) -> List[Dict[str, Any]]:
	if not is_configured():
		return []

	params = {
		"site_id": settings.PLAUSIBLE_SITE_ID,
		"period": period,
		"property": "event:page",
		"metrics": "pageviews,visitors",
		"limit": str(limit),
	}
	data = _get("breakdown", params)
	return data.get("results", []) or []
