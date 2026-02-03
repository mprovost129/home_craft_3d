from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.core.cache import cache

from .models import SiteConfig

CACHE_KEY = "core:site_config:v1"
CACHE_TTL_SECONDS = 30  # short TTL so admin changes take effect quickly


def get_site_config(*, use_cache: bool = True) -> SiteConfig:
    """
    Returns the singleton SiteConfig.

    Fresh DB case: auto-creates one row with model defaults.
    This avoids boot errors on a brand-new DB.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY)
        if isinstance(cached, SiteConfig):
            return cached

    obj = SiteConfig.objects.first()
    if obj is None:
        obj = SiteConfig.objects.create()

    cache.set(CACHE_KEY, obj, CACHE_TTL_SECONDS)
    return obj


def invalidate_site_config_cache() -> None:
    cache.delete(CACHE_KEY)


def get_marketplace_sales_percent() -> Decimal:
    cfg = get_site_config()
    return Decimal(cfg.marketplace_sales_percent or Decimal("0"))


def get_marketplace_sales_rate() -> Decimal:
    # 10.00 -> 0.10
    pct = get_marketplace_sales_percent()
    try:
        return (pct / Decimal("100"))
    except Exception:
        return Decimal("0")


def get_platform_fee_cents() -> int:
    cfg = get_site_config()
    try:
        return int(cfg.platform_fee_cents or 0)
    except Exception:
        return 0


def get_allowed_shipping_countries() -> list[str]:
    cfg = get_site_config()
    return cfg.allowed_shipping_countries
