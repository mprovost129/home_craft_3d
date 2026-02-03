from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages

from .models import SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "marketplace_sales_percent",
        "platform_fee_cents",
        "default_currency",
        "allowed_shipping_countries_csv",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # singleton: allow add only if none exists
        return not SiteConfig.objects.exists()

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """
        Convenience: if exactly one SiteConfig exists, jump directly to its edit page.
        """
        qs = SiteConfig.objects.all()
        if qs.count() == 1:
            obj = qs.first()
            url = reverse("admin:core_siteconfig_change", args=[obj.pk])
            return redirect(url)
        return super().changelist_view(request, extra_context=extra_context)
