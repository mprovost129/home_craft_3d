from __future__ import annotations

from decimal import Decimal
from typing import Dict, Tuple

from django.db import transaction

from .models import SiteSetting

# (default_value, description)
DEFAULTS: Dict[str, Tuple[str, str]] = {
    # Platform cut taken from sales (percent). Example: "10.0" => 10%
    "marketplace_sales_percent": ("10.0", "Platform cut of each sale, as a percent (e.g. 10.0)."),

    # You mentioned adding a platform fee later (flat fee). Leave default at 0 for now.
    "order_platform_fee_cents": ("0", "Optional flat fee per order in cents (0 disables)."),
}


def ensure_defaults_exist() -> None:
    """
    Ensures all DEFAULTS keys exist in the DB.
    Safe to call at runtime.
    """
    # Avoid wrapping in atomic unless you want strict consistency; this is fine.
    for key, (val, desc) in DEFAULTS.items():
        SiteSetting.objects.get_or_create(
            key=key,
            defaults={"value": val, "description": desc},
        )


def get_str(key: str, default: str = "") -> str:
    obj = SiteSetting.objects.filter(key=key).first()
    if obj is None:
        return default
    return (obj.value or "").strip()


def get_int(key: str, default: int = 0) -> int:
    obj = SiteSetting.objects.filter(key=key).first()
    if obj is None:
        return default
    return obj.as_int(default=default)


def get_decimal(key: str, default: Decimal = Decimal("0")) -> Decimal:
    obj = SiteSetting.objects.filter(key=key).first()
    if obj is None:
        return default
    return obj.as_decimal(default=default)


def get_bool(key: str, default: bool = False) -> bool:
    obj = SiteSetting.objects.filter(key=key).first()
    if obj is None:
        return default
    return obj.as_bool(default=default)


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
