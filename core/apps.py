# core/apps.py
from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    advertisement_banner = True  # Add AdvertisementBanner to core app config for migrations

    def ready(self) -> None:
        # ensure signals register
        from . import signals  # noqa: F401
