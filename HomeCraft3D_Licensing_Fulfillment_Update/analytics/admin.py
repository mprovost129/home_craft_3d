from __future__ import annotations

from django.contrib import admin

from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "path", "status_code", "user", "ip_hash")
    list_filter = ("event_type", "status_code", "created_at")
    search_fields = ("path", "referrer", "user_agent", "ip_hash", "session_key", "user__username", "user__email")
    ordering = ("-created_at",)
