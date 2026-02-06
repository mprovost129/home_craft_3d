from .models_advert import AdvertisementBanner
@admin.register(AdvertisementBanner)
class AdvertisementBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "start_date", "end_date", "created_at")
    list_filter = ("is_active", "start_date", "end_date")
    search_fields = ("title",)
from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.db.models import Sum, Count, Q
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from .models import SiteConfig
from orders.models import Order, OrderItem
from products.models import ProductEngagementEvent


# Extend the default admin site with analytics dashboard
class AnalyticsAdminSite(admin.AdminSite):
    """Default admin site with analytics dashboard."""
    
    def index(self, request: HttpRequest, extra_context=None) -> TemplateResponse:
        """Render dashboard with key metrics."""
        extra_context = extra_context or {}

        # All-time metrics
        total_orders = Order.objects.filter(status=Order.Status.PAID).count()
        total_revenue_cents = (
            Order.objects.filter(status=Order.Status.PAID)
            .aggregate(total=Sum("total_cents"))["total"] or 0
        )
        total_revenue = total_revenue_cents / 100

        # Last 30 days metrics
        thirty_days_ago = timezone.now() - timedelta(days=30)
        orders_30d = Order.objects.filter(
            status=Order.Status.PAID, paid_at__gte=thirty_days_ago
        ).count()
        revenue_30d_cents = (
            Order.objects.filter(status=Order.Status.PAID, paid_at__gte=thirty_days_ago)
            .aggregate(total=Sum("total_cents"))["total"] or 0
        )
        revenue_30d = revenue_30d_cents / 100

        # Engagement metrics
        total_views = ProductEngagementEvent.objects.filter(
            event_type=ProductEngagementEvent.EventType.VIEW
        ).count()
        total_clicks = ProductEngagementEvent.objects.filter(
            event_type=ProductEngagementEvent.EventType.CLICK
        ).count()
        total_add_to_cart = ProductEngagementEvent.objects.filter(
            event_type=ProductEngagementEvent.EventType.ADD_TO_CART
        ).count()

        # Top products by revenue
        top_products = (
            OrderItem.objects
            .filter(order__status=Order.Status.PAID)
            .values("product__id", "product__title", "product__seller__username")
            .annotate(
                quantity=Count("id"),
                revenue_cents=Sum("unit_price_cents"),
            )
            .order_by("-revenue_cents")[:10]
        )

        # Top products by engagement
        top_engagement = (
            ProductEngagementEvent.objects
            .values("product__id", "product__title")
            .annotate(
                events=Count("id"),
                views=Count("id", filter=Q(event_type=ProductEngagementEvent.EventType.VIEW)),
                clicks=Count("id", filter=Q(event_type=ProductEngagementEvent.EventType.CLICK)),
                add_to_cart=Count("id", filter=Q(event_type=ProductEngagementEvent.EventType.ADD_TO_CART)),
            )
            .order_by("-events")[:10]
        )

        # Convert revenue to formatted display
        extra_context.update({
            "total_orders": total_orders,
            "total_revenue": f"${total_revenue:,.2f}",
            "orders_30d": orders_30d,
            "revenue_30d": f"${revenue_30d:,.2f}",
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_add_to_cart": total_add_to_cart,
            "top_products": list(top_products),
            "top_engagement": list(top_engagement),
        })
        return super().index(request, extra_context)


# Extend the default admin site with analytics
admin.site.__class__ = AnalyticsAdminSite


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "marketplace_sales_percent",
        "platform_fee_cents",
        "default_currency",
        "theme_default_mode",
        "allowed_shipping_countries_csv",
        "updated_at",
    )

    class Media:
        css = {
            'all': ('admin/css/custom.css',)
        }

    fieldsets = (
        ("Commerce", {"fields": ("marketplace_sales_percent", "platform_fee_cents", "default_currency")}),
        ("Shipping", {"fields": ("allowed_shipping_countries",)}),
        (
            "Theme",
            {
                "fields": (
                    "theme_default_mode",
                    "theme_primary",
                    "theme_accent",
                    "theme_success",
                    "theme_danger",
                )
            },
        ),
        (
            "Theme (Light Mode)",
            {
                "fields": (
                    "theme_light_bg",
                    "theme_light_surface",
                    "theme_light_text",
                    "theme_light_text_muted",
                    "theme_light_border",
                )
            },
        ),
        (
            "Theme (Dark Mode)",
            {
                "fields": (
                    "theme_dark_bg",
                    "theme_dark_surface",
                    "theme_dark_text",
                    "theme_dark_text_muted",
                    "theme_dark_border",
                )
            },
        ),
        (
            "Social Links",
            {
                "fields": (
                    "facebook_url",
                    "instagram_url",
                    "tiktok_url",
                    "youtube_url",
                    "x_url",
                    "linkedin_url",
                )
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not SiteConfig.objects.exists()

    def changelist_view(self, request: HttpRequest, extra_context=None) -> TemplateResponse:
        qs = SiteConfig.objects.all()
        if qs.count() == 1:
            obj = qs.first()
            url = None
            if obj is not None:
                url = reverse("admin:core_siteconfig_change", args=[obj.pk])
            # Render a minimal template that performs the redirect via meta-refresh
            return TemplateResponse(
                request,
                "admin/redirect.html",
                {"redirect_url": url},
            )
        return super().changelist_view(request, extra_context=extra_context)