from __future__ import annotations

from django.contrib import admin
from .models import SellerStripeAccount


@admin.register(SellerStripeAccount)
class SellerStripeAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "stripe_account_id",
        "details_submitted",
        "charges_enabled",
        "payouts_enabled",
        "onboarding_started_at",
        "onboarding_completed_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "stripe_account_id")
    list_filter = ("details_submitted", "charges_enabled", "payouts_enabled")
