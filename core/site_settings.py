# core/site_settings.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Tuple

from django.db import transaction

from .models import SiteConfig

# (default_value, description)
DEFAULTS: Dict[str, Tuple[str, str]] = {
    # Platform cut taken from sales (percent). Example: "15.0" => 15%
    "marketplace_sales_percent": ("15.0", "Platform cut of each sale, as a percent (e.g. 15.0)."),

    # You mentioned adding a platform fee later (flat fee). Leave default at 0 for now.
    "order_platform_fee_cents": ("0", "Optional flat fee per order in cents (0 disables)."),
}


def ensure_defaults_exist() -> None:
    """
    Ensures all DEFAULTS keys exist in the DB.
    Safe to call at runtime.
    """
    # Avoid wrapping in atomic unless you want strict consistency; this is fine.
    SiteConfig.objects.get_or_create(pk=1)


def get_str(key: str, default: str = "") -> str:
    obj = SiteConfig.objects.filter(pk=1).first()
    if obj is None:
        return default
    val = getattr(obj, key, None)
    if val is None:
        return default
    return str(val).strip()


def get_int(key: str, default: int = 0) -> int:
    obj = SiteConfig.objects.filter(pk=1).first()
    if obj is None:
        return default
    try:
        val = getattr(obj, key, None)
        if val is None:
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def get_decimal(key: str, default: Decimal = Decimal("0")) -> Decimal:
    obj = SiteConfig.objects.filter(pk=1).first()
    if obj is None:
        return default
    try:
        val = getattr(obj, key, None)
        if val is None:
            return default
        return Decimal(str(val))
    except Exception:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    obj = SiteConfig.objects.filter(pk=1).first()
    if obj is None:
        return default
    try:
        val = getattr(obj, key, None)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")
    except Exception:
        return default


def marketplace_sales_percent() -> Decimal:
    """
    The sales cut percent (e.g. 10.0).
    """
    ensure_defaults_exist()
    return get_decimal("marketplace_sales_percent", default=Decimal(DEFAULTS["marketplace_sales_percent"][0]))


def marketplace_sales_rate() -> Decimal:
    """
    The sales cut rate (e.g. 0.10).
    """
    pct = marketplace_sales_percent()
    try:
        return (pct / Decimal("100"))
    except Exception:
        return Decimal("0.10")
