from __future__ import annotations

from django.contrib import admin

from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "host",
        "environment",
        "path",
        "status_code",
        "visitor_id",
        "session_id",
        "user",
        "is_staff",
    )
    list_filter = ("event_type", "status_code", "host", "environment", "is_staff", "created_at")
    search_fields = (
        "path",
        "referrer",
        "user_agent",
        "visitor_id",
        "session_id",
        "ip_hash",
        "session_key",
        "user__username",
        "user__email",
    )
    ordering = ("-created_at",)
