from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import models


class SiteConfig(models.Model):
    """
    DB-backed site settings (singleton).

    STRICT RULE:
    - Any site setting MUST live here (so it's editable via Django admin/dashboard).
    - No "settings.py constants" for runtime-tunable business rules.
    """

    # Marketplace fee: percent of seller gross (e.g. 10.00 -> 10%)
    marketplace_sales_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Percent of sales withheld by the marketplace (e.g., 10.00 = 10%).",
    )

    # Optional fixed platform fee in cents (kept here even if you start at 0)
    platform_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="Optional fixed fee in cents added to each order (0 disables).",
    )

    # Currency defaults
    default_currency = models.CharField(
        max_length=8,
        default="usd",
        help_text="Default currency (Stripe-style), e.g. 'usd'.",
    )

    # Shipping configuration
    # Store as JSON to avoid Postgres ArrayField dependency issues.
    allowed_shipping_countries = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed country codes for shipping (e.g. ['US']).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Config"
        verbose_name_plural = "Site Config"

    def __str__(self) -> str:
        return "SiteConfig"

    @property
    def allowed_shipping_countries_csv(self) -> str:
        try:
            codes = self.allowed_shipping_countries or []
            if not isinstance(codes, list):
                return ""
            cleaned = [str(x).strip().upper() for x in codes if str(x).strip()]
            return ",".join(cleaned)
        except Exception:
            return ""

    def clean(self) -> None:
        # Normalize JSON list field and defaults.
        try:
            codes = self.allowed_shipping_countries
            if not codes:
                self.allowed_shipping_countries = ["US"]
            elif isinstance(codes, list):
                cleaned = [str(x).strip().upper() for x in codes if str(x).strip()]
                self.allowed_shipping_countries = cleaned or ["US"]
            else:
                # If someone put a non-list in JSONField, reset safely
                self.allowed_shipping_countries = ["US"]
        except Exception:
            self.allowed_shipping_countries = ["US"]

        # Clamp percent to sane bounds
        try:
            pct = Decimal(self.marketplace_sales_percent or Decimal("0"))
        except Exception:
            pct = Decimal("0")

        if pct < 0:
            self.marketplace_sales_percent = Decimal("0.00")
        elif pct > 100:
            self.marketplace_sales_percent = Decimal("100.00")

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Ensure normalization runs even when changed in admin.
        self.clean()
        super().save(*args, **kwargs)

        # STRICT cache invalidation (no stale settings)
        try:
            from .config import invalidate_site_config_cache

            invalidate_site_config_cache()
        except Exception:
            pass
