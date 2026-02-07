# payments/apps.py
from __future__ import annotations

from django.apps import AppConfig

class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self) -> None:
        # Ensure signals register
        from . import signals  # noqa: F401
