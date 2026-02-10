# core/signals.py
from __future__ import annotations

from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .config import invalidate_site_config_cache
from .models import SiteConfig


@receiver(post_migrate)
def ensure_site_config(sender, **kwargs):
    """
    Ensure exactly one SiteConfig exists.

    Runs after migrations; safe on a brand-new database.
    """
    try:
        SiteConfig.objects.get_or_create(id=1, defaults={"allowed_shipping_countries": ["US"]})
    except Exception:
        # If PK=1 already taken or DB behavior differs, fall back to "first or create".
        if not SiteConfig.objects.exists():
            SiteConfig.objects.create(allowed_shipping_countries=["US"])

    invalidate_site_config_cache()
