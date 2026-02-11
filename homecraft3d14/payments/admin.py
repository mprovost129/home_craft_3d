# payments/admin.py

from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum

from .models import SellerBalanceEntry, SellerStripeAccount


@admin.register(SellerStripeAccount)
class SellerStripeAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "stripe_account_id",
        "details_submitted",
        "charges_enabled",
        "payouts_enabled",
        "current_balance",
        "onboarding_started_at",
        "onboarding_completed_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "stripe_account_id")
    list_filter = ("details_submitted", "charges_enabled", "payouts_enabled")

    def current_balance(self, obj):
        total = (
            SellerBalanceEntry.objects.filter(seller=obj.user)
            .aggregate(total=Sum("amount_cents"))
            .get("total")
            or 0
        )
        return f"${total / 100:,.2f}"

    current_balance.short_description = "Balance"


@admin.register(SellerBalanceEntry)
class SellerBalanceEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "seller",
        "amount_cents",
        "reason",
        "order",
        "order_item",
        "note",
    )
    list_filter = ("reason", "created_at")
    search_fields = (
        "seller__username",
        "seller__email",
        "order__id",
        "note",
    )
    readonly_fields = (
        "seller",
        "amount_cents",
        "reason",
        "order",
        "order_item",
        "note",
        "created_at",
    )
