# core/models.py
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

    # -------------------------
    # Site-wide Promo Banner (above navbar, sitewide)
    # -------------------------
    promo_banner_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show a promo banner above the navbar sitewide.",
    )
    promo_banner_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Text shown in the promo banner. Keep it short.",
    )

    # -------------------------
    # Home Page Banner (home page only)
    # -------------------------
    home_banner_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show a banner on the home page (only).",
    )
    home_banner_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Text shown in the home page banner. Keep it short.",
    )

    # -------------------------
    # Seller fee waiver (on platform cut only; Stripe fees still apply)
    # -------------------------
    seller_fee_waiver_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, new sellers receive a temporary 0% marketplace cut.",
    )
    seller_fee_waiver_days = models.PositiveIntegerField(
        default=30,
        help_text="Length of new-seller fee waiver window in days.",
    )

    # -------------------------
    # Affiliate / Amazon Associates (sitewide)
    # -------------------------
    affiliate_links_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show affiliate product links (e.g., Amazon Associates) in the store sidebar.",
    )
    affiliate_links_title = models.CharField(
        max_length=80,
        blank=True,
        default="Recommended Filament & Gear",
        help_text="Sidebar section heading for affiliate links.",
    )
    affiliate_disclosure_text = models.CharField(
        max_length=240,
        blank=True,
        default="As an Amazon Associate I earn from qualifying purchases.",
        help_text="Short disclosure shown under the affiliate links (recommended).",
    )
    affiliate_links = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of links shown in the sidebar. Example item: "
            "{'label':'SUNLU PLA 1kg','url':'https://...','note':'Budget PLA+'} "
            "(label+url required; note optional)."
        ),
    )

    # Home page hero (marketing copy)
    home_hero_title = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Home page hero headline (left side).",
    )
    home_hero_subtitle = models.TextField(
        blank=True,
        default="",
        help_text="Home page hero paragraph (left side).",
    )

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

    plausible_shared_url = models.URLField(
        blank=True,
        default="",
        help_text="Plausible shared dashboard URL (read-only). Example: https://plausible.io/share/<site>?auth=...",
    )

    # -------------------------
    # Theme / Branding (Palette A + Light/Dark)
    # -------------------------
    class ThemeMode(models.TextChoices):
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    theme_default_mode = models.CharField(
        max_length=10,
        choices=ThemeMode.choices,
        default=ThemeMode.LIGHT,
        help_text="Default mode for new visitors (users may toggle).",
    )

    # Brand tokens (Palette A)
    theme_primary = models.CharField(
        max_length=20,
        default="#F97316",  # burnt orange
        help_text="Primary action color (hex).",
    )
    theme_accent = models.CharField(
        max_length=20,
        default="#F97316",  # same as primary keeps it tight
        help_text="Accent color (hex).",
    )
    theme_success = models.CharField(
        max_length=20,
        default="#16A34A",
        help_text="Success color (hex).",
    )
    theme_danger = models.CharField(
        max_length=20,
        default="#DC2626",
        help_text="Danger color (hex).",
    )

    # Light mode surfaces
    theme_light_bg = models.CharField(
        max_length=20,
        default="#F9FAFB",
        help_text="Light mode background (hex).",
    )
    theme_light_surface = models.CharField(
        max_length=20,
        default="#FFFFFF",
        help_text="Light mode surface/card background (hex).",
    )
    theme_light_text = models.CharField(
        max_length=20,
        default="#111827",
        help_text="Light mode text color (hex).",
    )
    theme_light_text_muted = models.CharField(
        max_length=20,
        default="#6B7280",
        help_text="Light mode muted text (hex).",
    )
    theme_light_border = models.CharField(
        max_length=20,
        default="#E5E7EB",
        help_text="Light mode border color (hex).",
    )

    # Dark mode surfaces
    theme_dark_bg = models.CharField(
        max_length=20,
        default="#0B1220",
        help_text="Dark mode background (hex).",
    )
    theme_dark_surface = models.CharField(
        max_length=20,
        default="#111B2E",
        help_text="Dark mode surface/card background (hex).",
    )
    theme_dark_text = models.CharField(
        max_length=20,
        default="#EAF0FF",
        help_text="Dark mode text color (hex).",
    )
    theme_dark_text_muted = models.CharField(
        max_length=20,
        default="#9FB0D0",
        help_text="Dark mode muted text (hex).",
    )
    theme_dark_border = models.CharField(
        max_length=20,
        default="#22304D",
        help_text="Dark mode border color (hex).",
    )

    # Social media links (optional)
    facebook_url = models.URLField(blank=True, default="", help_text="Optional Facebook page URL for footer icon.")
    instagram_url = models.URLField(blank=True, default="", help_text="Optional Instagram profile URL for footer icon.")
    tiktok_url = models.URLField(blank=True, default="", help_text="Optional TikTok profile URL for footer icon.")
    youtube_url = models.URLField(blank=True, default="", help_text="Optional YouTube channel URL for footer icon.")
    x_url = models.URLField(blank=True, default="", help_text="Optional X (Twitter) profile URL for footer icon.")
    linkedin_url = models.URLField(blank=True, default="", help_text="Optional LinkedIn page URL for footer icon.")

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

        # Clamp waiver days to sane bounds
        try:
            d = int(self.seller_fee_waiver_days or 0)
        except Exception:
            d = 0
        if d < 0:
            self.seller_fee_waiver_days = 0
        elif d > 365:
            self.seller_fee_waiver_days = 365

        # Banner housekeeping: clear text if checkbox is not checked
        self.promo_banner_text = (self.promo_banner_text or "").strip()
        if not self.promo_banner_enabled:
            self.promo_banner_text = ""

        self.home_banner_text = (self.home_banner_text or "").strip()
        if not self.home_banner_enabled:
            self.home_banner_text = ""

        # Affiliate links normalization
        self.affiliate_links_title = (self.affiliate_links_title or "").strip() or "Recommended Filament & Gear"
        self.affiliate_disclosure_text = (self.affiliate_disclosure_text or "").strip()

        cleaned_links: list[dict[str, str]] = []
        try:
            raw = self.affiliate_links or []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label", "") or "").strip()
                    url = str(item.get("url", "") or "").strip()
                    note = str(item.get("note", "") or "").strip()
                    if not label or not url:
                        continue
                    cleaned_links.append({"label": label, "url": url, "note": note})
        except Exception:
            cleaned_links = []

        self.affiliate_links = cleaned_links

        # If disabled, keep data but ensure title is sane; you can decide later to blank it.
        # We won't auto-clear links so you can toggle on/off without losing work.

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

        # STRICT cache invalidation (no stale settings)
        try:
            from .config import invalidate_site_config_cache

            invalidate_site_config_cache()
        except Exception:
            pass
