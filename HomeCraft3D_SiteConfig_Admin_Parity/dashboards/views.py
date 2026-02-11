# dashboards/views.py

from __future__ import annotations

from typing import Any
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re

from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, IntegerField, Sum, Exists, OuterRef, Value, Case, When
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.templatetags.static import static
from django.utils.timezone import localdate
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.config import get_site_config, invalidate_site_config_cache
from core.models import SiteConfig
from .forms import SiteConfigForm, ProductFreeUnlockForm
from .analytics import get_summary as analytics_get_summary
from .analytics import get_top_pages as analytics_get_top_pages
from .analytics import get_throttle_summary as analytics_get_throttle_summary
from .analytics import get_top_throttle_rules as analytics_get_top_throttle_rules
from .analytics import is_configured as analytics_is_configured
from orders.models import Order, OrderItem, OrderEvent, StripeWebhookDelivery, SellerFulfillmentTask
from refunds.models import RefundRequest, RefundAttempt
from payments.models import SellerStripeAccount, SellerBalanceEntry
from products.models import Product, ProductEngagementEvent, ProductDownloadEvent
from products.permissions import is_owner_user, is_seller_user
from payments.services import get_seller_balance_cents

from notifications.models import Notification
from notifications.services import notify_email_and_in_app


DASH_RECENT_DAYS = 30

# Keep in sync with core.views
HOME_ANON_CACHE_KEY = "home_html_anon_v2"

today = localdate()

def _cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(int(cents or 0)) / Decimal("100")).quantize(Decimal("0.01"))


def _build_analytics_link_url(url: str) -> str:
    """Return a safe analytics dashboard URL for templates.

    For Google Analytics we do not embed via iframes in-app (avoids CSP/cookie issues).
    We expose a simple outbound link if configured.
    """
    return (url or "").strip()


def _analytics_time_range_from_request(request):
    """Parse analytics range filters from query params.

    Supported:
      - a_range=today|7d|30d|custom  (default 30d)
      - a_start=YYYY-MM-DD (for custom)
      - a_end=YYYY-MM-DD   (for custom, inclusive)
    Returns: (start_dt, end_dt_exclusive, range_key, label, start_date, end_date)
    """
    from django.utils import timezone
    from django.utils.timezone import localdate

    range_key = (request.GET.get("a_range") or "30d").strip().lower()
    tz = timezone.get_current_timezone()
    now = timezone.now()

    def _midnight_aware(d):
        return timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 0, 0, 0), tz)

    start_dt = None
    end_dt = None
    start_date = None
    end_date = None
    label = "Last 30 days"

    if range_key == "today":
        start_date = localdate()
        end_date = start_date
        start_dt = _midnight_aware(start_date)
        end_dt = start_dt + timezone.timedelta(days=1)
        label = "Today"
    elif range_key == "7d":
        start_dt = now - timezone.timedelta(days=7)
        label = "Last 7 days"
    elif range_key == "30d":
        start_dt = now - timezone.timedelta(days=30)
        label = "Last 30 days"
    elif range_key == "custom":
        raw_start = (request.GET.get("a_start") or "").strip()
        raw_end = (request.GET.get("a_end") or "").strip()
        try:
            if raw_start:
                start_date = timezone.datetime.fromisoformat(raw_start).date()
            if raw_end:
                end_date = timezone.datetime.fromisoformat(raw_end).date()
        except Exception:
            # Leave as None; view will fall back.
            start_date = None
            end_date = None

        if start_date and end_date and end_date >= start_date:
            start_dt = _midnight_aware(start_date)
            end_dt = _midnight_aware(end_date) + timezone.timedelta(days=1)
            label = f"{start_date.isoformat()} → {end_date.isoformat()}"
        else:
            # Fall back to 30d if custom is invalid.
            range_key = "30d"
            start_dt = now - timezone.timedelta(days=30)
            label = "Last 30 days"
            start_date = None
            end_date = None
    else:
        range_key = "30d"
        start_dt = now - timezone.timedelta(days=30)
        label = "Last 30 days"

    return start_dt, end_dt, range_key, label, start_date, end_date






def dashboard_home(request):
    user = request.user

    if is_owner_user(user):
        return redirect("dashboards:admin")

    if is_seller_user(user):
        return redirect("dashboards:seller")

    return redirect("dashboards:consumer")


@login_required
def consumer_dashboard(request):
    user = request.user

    orders = (
        Order.objects.filter(buyer=user)
        .prefetch_related("items", "items__product")
        .order_by("-created_at")[:10]
    )

    totals = Order.objects.filter(buyer=user, status=Order.Status.PAID).aggregate(
        total_spent_cents=Sum("total_cents"),
        paid_count=Count("id"),
    )

    total_spent = _cents_to_dollars(int(totals.get("total_spent_cents") or 0))

    return render(
        request,
        "dashboards/consumer_dashboard.html",
        {
            "orders": orders,
            "total_spent": total_spent,
            "paid_count": totals.get("paid_count") or 0,
        },
    )


@login_required
def seller_dashboard(request):
    user = request.user

    if not is_seller_user(user):
        messages.info(request, "You don’t have access to the seller dashboard.")
        return redirect("dashboards:consumer")

    # Handle bulk activate/deactivate POST
    if request.method == "POST":
        action = request.POST.get("bulk_action")
        selected_ids = request.POST.getlist("selected_ids")
        if action in {"activate", "deactivate"} and selected_ids:
            products = Product.objects.filter(seller=user, id__in=selected_ids)
            new_status = action == "activate"
            updated = products.update(is_active=new_status)
            messages.success(request, f"{updated} listing(s) {'activated' if new_status else 'deactivated'}.")
            return redirect("dashboards:seller")

    # Use local time for analytics (America/New_York)
    from django.utils.timezone import localtime
    since = localtime(timezone.now()) - timedelta(days=DASH_RECENT_DAYS)

    stripe_obj, _ = SellerStripeAccount.objects.get_or_create(user=user)
    balance_cents = get_seller_balance_cents(seller=user)

    listings_total = Product.objects.filter(seller=user, is_active=True).count()
    listings_inactive = Product.objects.filter(seller=user, is_active=False).count()

    open_fulfillment_tasks_qs = SellerFulfillmentTask.objects.filter(seller=user, is_completed=False).select_related('order').order_by('-created_at')
    open_fulfillment_tasks_count = open_fulfillment_tasks_qs.count()
    open_fulfillment_tasks_preview = []
    for t in open_fulfillment_tasks_qs[:5]:
        pending_count = OrderItem.objects.filter(order=t.order, seller=user, requires_shipping=True, fulfillment_status=OrderItem.FulfillmentStatus.PENDING).count()
        open_fulfillment_tasks_preview.append({"task": t, "pending_count": pending_count})

    listings = Product.objects.filter(seller=user).prefetch_related("images", "digital_assets", "digital", "physical")

    def get_listing_checklist(product):
        return {
            "has_image": product.images.exists(),
            "has_specs": product.has_specs,
            "has_assets": product.digital_assets.exists() if product.kind == product.Kind.FILE else True,
            "is_active": product.is_active,
        }

    listings_with_checklist = [{"product": p, "checklist": get_listing_checklist(p)} for p in listings]

    line_total_expr = ExpressionWrapper(
        F("quantity") * F("unit_price_cents"),
        output_field=IntegerField(),
    )

    recent_sales = (
        OrderItem.objects.filter(
            seller=user,
            order__status=Order.Status.PAID,
            order__paid_at__gte=since,
        )
        .select_related("order", "product")
        .annotate(line_total_cents=line_total_expr)
        .order_by("-created_at")[:15]
    )

    sales_totals = OrderItem.objects.filter(
        seller=user,
        order__status=Order.Status.PAID,
        order__paid_at__gte=since,
    ).aggregate(
        gross_cents=Sum(line_total_expr),
        net_cents=Sum("seller_net_cents"),
        order_count=Count("order_id", distinct=True),
        sold_count=Sum("quantity"),
        refunded_count=Sum(Case(When(refund_request__status=RefundRequest.Status.REFUNDED, then=F("quantity")), default=Value(0), output_field=IntegerField())),
    )

    net_sold_count = int(sales_totals.get('sold_count') or 0) - int(sales_totals.get('refunded_count') or 0)

    payout_available_cents = max(0, int(balance_cents))

    ledger_entries = SellerBalanceEntry.objects.filter(seller=user).order_by("-created_at")[:10]

    balance_dollars = _cents_to_dollars(balance_cents)
    payout_available_dollars = _cents_to_dollars(payout_available_cents)

    grant_form = None
    if request.method == "POST" and "grant_free_download" in request.POST:
        grant_form = ProductFreeUnlockForm(request.POST, seller=user)
        if grant_form.is_valid():
            unlock, created = grant_form.save(user)
            if created:
                if grant_form.cleaned_data.get("send_email"):
                    recipient = grant_form.cleaned_data["user_email"]
                    recipient_user = grant_form.cleaned_data.get("user")
                    product = grant_form.cleaned_data["product"]
                    # LOCKED: all emails also create in-app notifications.
                    if recipient_user and getattr(recipient_user, "email", None):
                        subject = f"Free Download Unlocked: {product.title}"
                        logo_url = request.build_absolute_uri(static("images/homecraft3d_icon.svg"))
                        notify_email_and_in_app(
                            user=recipient_user,
                            kind=Notification.Kind.SYSTEM,
                            email_subject=subject,
                            email_template_html="emails/free_unlock.html",
                            email_template_txt=None,
                            context={
                                "subject": subject,
                                "logo_url": logo_url,
                                "product": product,
                                "seller": user,
                            },
                            title=f"Free download unlocked: {product.title}",
                            body=f"You have been granted a free download for {product.title}.",
                            action_url=product.get_absolute_url(),
                            payload={"product_id": product.pk, "granted_by": user.pk},
                        )
                    else:
                        send_mail(
                            subject=f"Free Download Unlocked: {product.title}",
                            message=f"You have been granted a free download for {product.title}.",
                            from_email=None,
                            recipient_list=[recipient],
                            fail_silently=True,
                        )
                messages.success(request, "Free download unlocked and user notified.")
            else:
                messages.info(request, "User already has free access to this product.")
            return redirect("dashboards:seller")
    else:
        grant_form = ProductFreeUnlockForm(seller=user)

    open_fulfillment_tasks = (
        SellerFulfillmentTask.objects.filter(seller=user, is_completed=False)
        .select_related("order")
        .order_by("-created_at")
    )
    open_fulfillment_tasks_count = open_fulfillment_tasks.count()
    open_fulfillment_tasks_preview = []
    for t in open_fulfillment_tasks[:5]:
        pending_count = OrderItem.objects.filter(
            order=t.order,
            seller=user,
            requires_shipping=True,
            fulfillment_status=OrderItem.FulfillmentStatus.PENDING,
        ).count()
        open_fulfillment_tasks_preview.append({"task": t, "pending_count": pending_count})

    return render(
        request,
        "dashboards/seller_dashboard.html",
        {
            "stripe": stripe_obj,
            "ready": stripe_obj.is_ready,
            "listings_total": listings_total,
            "listings_inactive": listings_inactive,
            "listings_with_checklist": listings_with_checklist,
            "recent_sales": recent_sales,
            "gross_revenue": _cents_to_dollars(int(sales_totals.get("gross_cents") or 0)),
            "net_revenue": _cents_to_dollars(int(sales_totals.get("net_cents") or 0)),
            "balance": balance_dollars,
            "balance_abs": abs(balance_dollars),
            "payout_available": payout_available_dollars,
            "payout_available_abs": abs(payout_available_dollars),
            "ledger_entries": ledger_entries,
            "sold_count": net_sold_count,
            "order_count": sales_totals.get("order_count") or 0,
            "open_fulfillment_tasks_count": open_fulfillment_tasks_count,
            "open_fulfillment_tasks_preview": open_fulfillment_tasks_preview,
            "since_days": DASH_RECENT_DAYS,
            "grant_form": grant_form,
        },
    )


@login_required

def seller_analytics(request):
    user = request.user
    if not is_seller_user(user):
        messages.info(request, "You don’t have access to seller analytics.")
        return redirect("dashboards:consumer")

    try:
        days = int(request.GET.get("days") or 30)
    except Exception:
        days = 30
    if days not in (7, 30, 90):
        days = 30

    # Local time for analytics (America/New_York)
    from django.utils.timezone import localtime
    since = localtime(timezone.now()) - timedelta(days=days)

    # --- Engagement (views/clicks/add-to-cart) ---
    engagement_qs = ProductEngagementEvent.objects.filter(
        product__seller=user,
        created_at__gte=since,
    )
    engagement_totals = {
        row["event_type"]: int(row["c"] or 0)
        for row in engagement_qs.values("event_type").annotate(c=Count("id"))
    }
    total_views = engagement_totals.get(ProductEngagementEvent.EventType.VIEW, 0)
    total_clicks = engagement_totals.get(ProductEngagementEvent.EventType.CLICK, 0)
    total_add_to_cart = engagement_totals.get(ProductEngagementEvent.EventType.ADD_TO_CART, 0)

    # --- Downloads (bundle/product-level) ---
    downloads_qs = ProductDownloadEvent.objects.filter(
        product__seller=user,
        created_at__gte=since,
    )
    downloads_total = downloads_qs.count()
    unique_user_downloaders = downloads_qs.exclude(user__isnull=True).values("user_id").distinct().count()
    unique_session_downloaders = downloads_qs.filter(user__isnull=True).exclude(session_key="").values("session_key").distinct().count()
    downloads_unique = int(unique_user_downloaders) + int(unique_session_downloaders)

    # --- Sales (paid minus refunded) ---
    line_total_expr = ExpressionWrapper(
        F("quantity") * F("unit_price_cents"),
        output_field=IntegerField(),
    )

    paid_items_qs = OrderItem.objects.filter(
        seller=user,
        is_tip=False,
        order__status=Order.Status.PAID,
        order__paid_at__gte=since,
    )

    paid_totals = paid_items_qs.aggregate(
        paid_qty=Sum("quantity"),
        gross_cents=Sum(line_total_expr),
        net_cents=Sum("seller_net_cents"),
        order_count=Count("order_id", distinct=True),
    )
    paid_qty = int(paid_totals["paid_qty"] or 0)

    refunded_items_qs = OrderItem.objects.filter(
        seller=user,
        is_tip=False,
        refund_request__status=RefundRequest.Status.REFUNDED,
        refund_request__refunded_at__gte=since,
    )
    refunded_qty = int(refunded_items_qs.aggregate(qty=Sum("quantity"))["qty"] or 0)

    net_units_sold = max(0, paid_qty - refunded_qty)

    # --- Per product table data ---
    products = (
        Product.objects.filter(seller=user)
        .select_related("category")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    # engagement per product per type
    per_eng = {}
    for row in engagement_qs.values("product_id", "event_type").annotate(c=Count("id")):
        per_eng.setdefault(row["product_id"], {})[row["event_type"]] = int(row["c"] or 0)

    # downloads per product
    per_dl_total = {row["product_id"]: int(row["c"] or 0) for row in downloads_qs.values("product_id").annotate(c=Count("id"))}
    per_dl_user_unique = {row["product_id"]: int(row["c"] or 0) for row in downloads_qs.exclude(user__isnull=True).values("product_id").annotate(c=Count("user_id", distinct=True))}
    per_dl_sess_unique = {row["product_id"]: int(row["c"] or 0) for row in downloads_qs.filter(user__isnull=True).exclude(session_key="").values("product_id").annotate(c=Count("session_key", distinct=True))}

    # sales per product
    per_paid_qty = {row["product_id"]: int(row["qty"] or 0) for row in paid_items_qs.values("product_id").annotate(qty=Sum("quantity"))}
    per_ref_qty = {row["product_id"]: int(row["qty"] or 0) for row in refunded_items_qs.values("product_id").annotate(qty=Sum("quantity"))}

    per_rows = []
    for p in products:
        eng = per_eng.get(p.pk, {})
        views = int(eng.get(ProductEngagementEvent.EventType.VIEW, 0))
        clicks = int(eng.get(ProductEngagementEvent.EventType.CLICK, 0))
        adds = int(eng.get(ProductEngagementEvent.EventType.ADD_TO_CART, 0))
        paid_q = per_paid_qty.get(p.pk, 0)
        ref_q = per_ref_qty.get(p.pk, 0)
        net_sold = max(0, int(paid_q) - int(ref_q))

        dl_total = per_dl_total.get(p.pk, 0)
        dl_unique = per_dl_user_unique.get(p.pk, 0) + per_dl_sess_unique.get(p.pk, 0)

        per_rows.append(
            {
                "product": p,
                "views": views,
                "clicks": clicks,
                "add_to_cart": adds,
                "paid_qty": paid_q,
                "refunded_qty": ref_q,
                "net_units_sold": net_sold,
                "downloads_total": dl_total,
                "downloads_unique": dl_unique,
            }
        )

    context = {
        "days": days,
        "since": since,
        "total_views": total_views,
        "total_clicks": total_clicks,
        "total_add_to_cart": total_add_to_cart,
        "downloads_total": downloads_total,
        "downloads_unique": downloads_unique,
        "paid_qty": paid_qty,
        "refunded_qty": refunded_qty,
        "net_units_sold": net_units_sold,
            "open_fulfillment_tasks_count": open_fulfillment_tasks_count,
            "open_fulfillment_tasks_preview": open_fulfillment_tasks_preview,
        "gross_dollars": _cents_to_dollars(int(paid_totals["gross_cents"] or 0)),
        "net_dollars": _cents_to_dollars(int(paid_totals["net_cents"] or 0)),
        "order_count": int(paid_totals["order_count"] or 0),
        "rows": per_rows,
    }
    return render(request, "dashboards/seller_analytics.html", context)



@login_required
def seller_payouts(request):
    user = request.user
    if not is_seller_user(user) and not is_owner_user(user):
        return redirect("dashboards:home")

    # Owner can view their own payouts page as a seller if desired.
    seller = user

    # Ledger balance (available within platform accounting)
    available_cents = int(get_seller_balance_cents(seller) or 0)

    # Pending: paid orders for this seller that do not yet have a TRANSFER_CREATED event.
    transfer_exists = OrderEvent.objects.filter(
        order_id=OuterRef("order_id"),
        type=OrderEvent.Type.TRANSFER_CREATED,
    )

    pending_qs = (
        OrderItem.objects.select_related("order", "product")
        .filter(seller=seller, order__status=Order.Status.PAID)
        .annotate(has_transfer=Exists(transfer_exists))
        .filter(has_transfer=False)
    )

    pending_cents = int(pending_qs.aggregate(total=Sum("seller_net_cents")).get("total") or 0)

    # Recent ledger entries for transparency
    ledger_entries = (
        SellerBalanceEntry.objects.filter(seller=seller)
        .select_related("order", "order_item")
        .order_by("-created_at")[:50]
    )

    context = {
        "available_cents": available_cents,
        "available_dollars": _cents_to_dollars(available_cents),
        "pending_cents": pending_cents,
        "pending_dollars": _cents_to_dollars(pending_cents),
        "ledger_entries": ledger_entries,
        "pending_items": pending_qs[:50],
    }
    
    # Abuse signals (native throttle events)
    abuse_24h = {}
    abuse_7d = {}
    abuse_top_rules_24h = []
    abuse_top_rules_7d = []

    try:
        now = timezone.now()
        abuse_24h = analytics_get_throttle_summary(start=now - timedelta(hours=24), end=now) or {}
        abuse_7d = analytics_get_throttle_summary(start=now - timedelta(days=7), end=now) or {}
        abuse_top_rules_24h = analytics_get_top_throttle_rules(start=now - timedelta(hours=24), end=now, limit=8) or []
        abuse_top_rules_7d = analytics_get_top_throttle_rules(start=now - timedelta(days=7), end=now, limit=8) or []
    except Exception:
        abuse_24h = {}
        abuse_7d = {}
        abuse_top_rules_24h = []
        abuse_top_rules_7d = []

    return render(request, "dashboards/seller_payouts.html", context)



def admin_dashboard(request):
    user = request.user

    if not is_owner_user(user):
        messages.info(request, "You don’t have access to the admin dashboard.")
        return redirect("dashboards:consumer")

    # Use local time for analytics (America/New_York)
    from django.utils.timezone import localtime
    since = localtime(timezone.now()) - timedelta(days=DASH_RECENT_DAYS)

    cfg = get_site_config()
    analytics_dashboard_url = (getattr(cfg, "google_analytics_dashboard_url", "") or "").strip()
    site_config_admin_url = reverse("admin:core_siteconfig_changelist")

    products_total = Product.objects.count()
    products_active = Product.objects.filter(is_active=True).count()

    sellers_total = Product.objects.values("seller_id").distinct().count()

    orders_paid = Order.objects.filter(status=Order.Status.PAID, paid_at__isnull=False).count()
    orders_pending = Order.objects.filter(status=Order.Status.PENDING).count()

    revenue_cents = (
        Order.objects.filter(
            status=Order.Status.PAID,
            paid_at__isnull=False,
            paid_at__gte=since,
        ).aggregate(total=Sum("subtotal_cents"))
    ).get("total") or 0
    revenue_30 = _cents_to_dollars(int(revenue_cents))

    line_total_expr = ExpressionWrapper(
        F("quantity") * F("unit_price_cents"),
        output_field=IntegerField(),
    )

    top_sellers = (
        OrderItem.objects.filter(
            order__status=Order.Status.PAID,
            order__paid_at__isnull=False,
            order__paid_at__gte=since,
        )
        .values("seller__username")
        .annotate(
            revenue_cents=Sum(line_total_expr),
            qty=Sum("quantity"),
            orders=Count("order_id", distinct=True),
        )
        .order_by("-revenue_cents")[:10]
    )

    top_sellers_display = [
        {
            "seller__username": row.get("seller__username") or "",
            "revenue": _cents_to_dollars(int(row.get("revenue_cents") or 0)),
            "qty": row.get("qty") or 0,
            "orders": row.get("orders") or 0,
        }
        for row in top_sellers
    ]

    # -------------------------
    # Analytics (Native, server-side)
    # -------------------------
    analytics_enabled = bool(getattr(cfg, "analytics_enabled", True))
    analytics_retention_days = int(getattr(cfg, "analytics_retention_days", 90) or 90)

    analytics_summary_display: dict[str, Any] = {}
    analytics_top_pages: list[dict[str, Any]] = []
    analytics_api_error = ""

    # Range filters (today / 7d / 30d / custom)
    analytics_start_dt, analytics_end_dt, analytics_range_key, analytics_range_label, analytics_start_date, analytics_end_date = (
        _analytics_time_range_from_request(request)
    )

    if analytics_enabled:
        try:
            analytics_summary_display = analytics_get_summary(start=analytics_start_dt, end=analytics_end_dt) or {}
            analytics_top_pages = analytics_get_top_pages(start=analytics_start_dt, end=analytics_end_dt, limit=10) or []
        except Exception:
            analytics_api_error = "Native analytics aggregation failed."
            analytics_summary_display = {}
            analytics_top_pages = []
    return render(
        request,
        "dashboards/admin_dashboard.html",
        {
            "products_total": products_total,
            "products_active": products_active,
            "sellers_total": sellers_total,
            "orders_paid": orders_paid,
            "orders_pending": orders_pending,
            "revenue_30": revenue_30,
            "top_sellers": top_sellers_display,
            "since_days": DASH_RECENT_DAYS,
            "site_config_admin_url": site_config_admin_url,
            "marketplace_sales_percent": getattr(cfg, "marketplace_sales_percent", 0) or 0,
            "platform_fee_cents": int(getattr(cfg, "platform_fee_cents", 0) or 0),
            "analytics_dashboard_url": analytics_dashboard_url,
            "analytics_enabled": analytics_enabled,
            "analytics_retention_days": analytics_retention_days,
            "analytics_range_key": analytics_range_key,
            "analytics_range_label": analytics_range_label,
            "analytics_start_date": analytics_start_date,
            "analytics_end_date": analytics_end_date,
            "analytics_summary_display": analytics_summary_display,
            "analytics_top_pages": analytics_top_pages,
            "analytics_api_error": analytics_api_error,
        },
    )


@login_required
def admin_settings(request):
    user = request.user

    if not is_owner_user(user):
        messages.info(request, "You don’t have access to admin settings.")
        return redirect("dashboards:consumer")

    # IMPORTANT:
    # For editing, always use a fresh DB instance (not a cached object)
    cfg = SiteConfig.objects.first()
    if cfg is None:
        cfg = SiteConfig.objects.create()

    if request.method == "POST":
        form = SiteConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()

            # Bust SiteConfig cache AND anonymous home HTML cache (banner/theme changes)
            from contextlib import suppress
            with suppress(Exception):
                invalidate_site_config_cache()
            with suppress(Exception):
                cache.delete(HOME_ANON_CACHE_KEY)

            messages.success(request, "Settings updated.")
            return redirect("dashboards:admin_settings")
        else:
            messages.error(request, "Please fix the errors below and try again.")
    else:
        form = SiteConfigForm(instance=cfg)

    return render(
        request,
        "dashboards/admin_settings.html",
        {"form": form, "site_config_updated_at": getattr(cfg, "updated_at", None)},
    )




@login_required
def admin_ops(request):
    user = request.user
    if not is_owner_user(user):
        messages.info(request, "You don’t have access to admin ops.")
        return redirect("dashboards:consumer")

    since_7d = timezone.now() - timedelta(days=7)
    since_24h = timezone.now() - timedelta(hours=24)

    deliveries_qs = StripeWebhookDelivery.objects.filter(received_at__gte=since_7d)
    deliveries_counts_raw = deliveries_qs.values("status").annotate(count=Count("id"))
    deliveries_counts = {row["status"]: int(row["count"] or 0) for row in deliveries_counts_raw}

    webhook_errors = deliveries_qs.filter(status="error").order_by("-received_at")[:25]

    attempts_qs = RefundAttempt.objects.filter(created_at__gte=since_7d)
    attempts_counts_raw = attempts_qs.values("success").annotate(count=Count("id"))
    refund_attempt_counts = {"success": 0, "error": 0}
    for row in attempts_counts_raw:
        if row["success"]:
            refund_attempt_counts["success"] = int(row["count"] or 0)
        else:
            refund_attempt_counts["error"] = int(row["count"] or 0)

    refund_failures_24h = RefundAttempt.objects.filter(success=False, created_at__gte=since_24h).order_by("-created_at")[:25]

    recent_order_warnings = (
        OrderEvent.objects.filter(type=OrderEvent.Type.WARNING, created_at__gte=since_7d)
        .select_related("order")
        .order_by("-created_at")[:25]
    )

    return render(
        request,
        "dashboards/admin_ops.html",
        {
            "since_7d": since_7d,
            "deliveries_counts": deliveries_counts,
            "webhook_errors": webhook_errors,
            "refund_attempt_counts": refund_attempt_counts,
            "refund_failures_24h": refund_failures_24h,
            "recent_order_warnings": recent_order_warnings,
        },
    )



@login_required
def ajax_verify_username(request):
    """AJAX endpoint to verify username and return email if user exists."""
    username = request.GET.get("username", "").strip()
    User = get_user_model()
    try:
        user = User.objects.get(username=username, is_active=True)
        return JsonResponse({"success": True, "email": user.email})
    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "No active user found with this username."})
