# notifications/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "user",
        "kind",
        "title",
        "is_read",
        "read_at",
    )
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("id", "user__username", "user__email", "title", "body", "email_subject")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "read_at")
