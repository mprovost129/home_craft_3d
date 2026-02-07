# core/admin.py
from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.mail import send_mass_mail
from django.db.models import Sum, Count, Q
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from .models import SiteConfig
from orders.models import Order, OrderItem
from products.models import ProductEngagementEvent
from .models_advert import AdvertisementBanner
from .models_email import SiteEmailTemplate


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


admin.site.__class__ = AnalyticsAdminSite


class SiteEmailTemplateInline(admin.TabularInline):
    model = SiteEmailTemplate
    extra = 0
    fields = ("name", "subject", "is_active", "updated_at")
    readonly_fields = ("updated_at",)
    show_change_link = True


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    inlines = [SiteEmailTemplateInline]
    list_display = (
        "id",
        "promo_banner_enabled",
        "marketplace_sales_percent",
        "seller_fee_waiver_enabled",
        "seller_fee_waiver_days",
        "platform_fee_cents",
        "default_currency",
        "theme_default_mode",
        "allowed_shipping_countries_csv",
        "updated_at",
    )

    class Media:
        css = {
            "all": ("admin/css/custom.css",)
        }

    fieldsets = (
        ("Promo Banner", {"fields": ("promo_banner_enabled", "promo_banner_text")}),
        ("Seller Promo (Fee Waiver)", {"fields": ("seller_fee_waiver_enabled", "seller_fee_waiver_days")}),
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
        ("Analytics", {"fields": ("plausible_shared_url",)}),
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
            return TemplateResponse(
                request,
                "admin/redirect.html",
                {"redirect_url": url},
            )
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(AdvertisementBanner)
class AdvertisementBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "start_date", "end_date", "created_at")
    list_filter = ("is_active", "start_date", "end_date")
    search_fields = ("title",)


@admin.register(SiteEmailTemplate)
class SiteEmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "subject", "body")

    actions = ["send_email_to_all_users", "send_email_to_all_staff"]

    from django.template import Context, Template

    def render_template(self, raw, context_dict):
        return Template(raw).render(Context(context_dict))

    def send_email_to_all_users(self, request, queryset):
        User = get_user_model()
        users = User.objects.filter(is_active=True, email__isnull=False).exclude(email="")
        site_name = request.get_host()
        for template in queryset:
            datatuple = []
            for user in users:
                context = {"user": user.get_full_name() or user.username, "site_name": site_name}
                subject = self.render_template(template.subject, context)
                body = self.render_template(template.body, context)
                datatuple.append((subject, body, None, [user.email]))
            if datatuple:
                send_mass_mail(datatuple, fail_silently=False)
            self.message_user(request, f"Sent '{template.name}' to {len(datatuple)} users.", messages.SUCCESS)
    send_email_to_all_users.short_description = "Send selected template to all users"

    def send_email_to_all_staff(self, request, queryset):
        User = get_user_model()
        users = User.objects.filter(is_staff=True, is_active=True, email__isnull=False).exclude(email="")
        site_name = request.get_host()
        for template in queryset:
            datatuple = []
            for user in users:
                context = {"user": user.get_full_name() or user.username, "site_name": site_name}
                subject = self.render_template(template.subject, context)
                body = self.render_template(template.body, context)
                datatuple.append((subject, body, None, [user.email]))
            if datatuple:
                send_mass_mail(datatuple, fail_silently=False)
            self.message_user(request, f"Sent '{template.name}' to {len(datatuple)} staff members.", messages.SUCCESS)
    send_email_to_all_staff.short_description = "Send selected template to all staff"
