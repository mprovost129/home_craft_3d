from __future__ import annotations

from django.conf import settings
from django.db import models


class AnalyticsEvent(models.Model):
    class EventType(models.TextChoices):
        PAGEVIEW = "PAGEVIEW", "Pageview"

    event_type = models.CharField(max_length=32, choices=EventType.choices, default=EventType.PAGEVIEW)
    path = models.CharField(max_length=512, db_index=True)
    method = models.CharField(max_length=8, default="GET")
    status_code = models.PositiveIntegerField(default=200)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
    )
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)

    user_agent = models.CharField(max_length=400, blank=True, default="")
    referrer = models.CharField(max_length=512, blank=True, default="", db_index=True)

    meta = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["path", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.path}"
