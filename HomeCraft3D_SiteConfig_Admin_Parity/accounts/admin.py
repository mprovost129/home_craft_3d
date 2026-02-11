#accounts/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_seller", "stripe_onboarding_complete", "is_owner", "created_at")
    list_filter = ("is_seller", "stripe_onboarding_complete", "is_owner")
    search_fields = ("user__username", "email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at")
