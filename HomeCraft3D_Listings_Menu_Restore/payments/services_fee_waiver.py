# payments/services_fee_waiver.py
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from core.config import get_site_config
from payments.models import SellerFeeWaiver


def get_effective_marketplace_sales_percent_for_seller(*, seller_user) -> Decimal:
    """
    Returns the marketplace sales percent for a seller, after applying fee-waiver logic.

    - If waiver enabled and seller has an active waiver window => 0%
    - Else => SiteConfig.marketplace_sales_percent
    """
    cfg = get_site_config()
    default_pct = Decimal(getattr(cfg, "marketplace_sales_percent", Decimal("0.00")) or Decimal("0.00"))

    waiver_enabled = bool(getattr(cfg, "seller_fee_waiver_enabled", True))
    if not waiver_enabled:
        return default_pct

    waiver = SellerFeeWaiver.objects.filter(user=seller_user).first()
    if waiver and waiver.is_active:
        return Decimal("0.00")

    return default_pct


def ensure_fee_waiver_for_new_seller(*, seller_user) -> None:
    """
    Idempotently create a waiver record for a seller based on SiteConfig.seller_fee_waiver_days.
    """
    cfg = get_site_config()
    if not bool(getattr(cfg, "seller_fee_waiver_enabled", True)):
        return

    try:
        days = int(getattr(cfg, "seller_fee_waiver_days", 30) or 30)
    except Exception:
        days = 30

    days = max(0, min(days, 365))
    # Only create if missing
    if not SellerFeeWaiver.objects.filter(user=seller_user).exists():
        SellerFeeWaiver.ensure_for_seller(user=seller_user, waiver_days=days)
