# dashboards/views.py

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, IntegerField, Sum
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from core.config import get_site_config
from .forms import SiteConfigForm
from .plausible import get_summary as plausible_get_summary
from .plausible import get_top_pages as plausible_get_top_pages
from .plausible import is_configured as plausible_is_configured
from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount, SellerBalanceEntry
from products.models import Product
from products.permissions import is_owner_user, is_seller_user
from payments.services import get_seller_balance_cents


DASH_RECENT_DAYS = 30


def _cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(int(cents or 0)) / Decimal("100")).quantize(Decimal("0.01"))


def _build_plausible_embed_url(shared_url: str, *, theme: str = "light") -> str:
    """
    Plausible shared links embed by adding query params (not by swapping /share/ to /embed/).

    Example:
      https://plausible.io/share/homecraft3d.com?auth=XYZ
    becomes:
      https://plausible.io/share/homecraft3d.com?auth=XYZ&embed=true&theme=light
    """
    shared_url = (shared_url or "").strip()
    if not shared_url:
        return ""

    try:
        parsed = urlparse(shared_url)
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        qs["embed"] = "true"
        # theme is optional; Plausible supports light/dark
        if theme:
            qs["theme"] = theme

        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        # If anything odd happens, just don't embed.
        return ""


@login_required
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

    since = timezone.now() - timedelta(days=DASH_RECENT_DAYS)

    stripe_obj, _ = SellerStripeAccount.objects.get_or_create(user=user)
    balance_cents = get_seller_balance_cents(seller=user)

    listings_total = Product.objects.filter(seller=user, is_active=True).count()
    listings_inactive = Product.objects.filter(seller=user, is_active=False).count()

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
    )

    payout_available_cents = max(0, int((sales_totals.get("net_cents") or 0) + balance_cents))

    ledger_entries = SellerBalanceEntry.objects.filter(seller=user).order_by("-created_at")[:10]

    return render(
        request,
        "dashboards/seller_dashboard.html",
        {
            "stripe": stripe_obj,
            "ready": stripe_obj.is_ready,
            "listings_total": listings_total,
            "listings_inactive": listings_inactive,
            "recent_sales": recent_sales,
            "gross_revenue": _cents_to_dollars(int(sales_totals.get("gross_cents") or 0)),
            "net_revenue": _cents_to_dollars(int(sales_totals.get("net_cents") or 0)),
            "balance": _cents_to_dollars(balance_cents),
            "payout_available": _cents_to_dollars(payout_available_cents),
            "ledger_entries": ledger_entries,
            "sold_count": sales_totals.get("sold_count") or 0,
            "order_count": sales_totals.get("order_count") or 0,
            "since_days": DASH_RECENT_DAYS,
        },
    )


@login_required
def admin_dashboard(request):
    user = request.user

    if not is_owner_user(user):
        messages.info(request, "You don’t have access to the admin dashboard.")
        return redirect("dashboards:consumer")

    since = timezone.now() - timedelta(days=DASH_RECENT_DAYS)

    cfg = get_site_config()
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

    top_sellers_display = []
    for row in top_sellers:
        top_sellers_display.append(
            {
                "seller__username": row.get("seller__username") or "",
                "revenue": _cents_to_dollars(int(row.get("revenue_cents") or 0)),
                "qty": row.get("qty") or 0,
                "orders": row.get("orders") or 0,
            }
        )

    # ---- Plausible (shared dashboard link + API stats) ----
    plausible_shared_url = (getattr(cfg, "plausible_shared_url", "") or "").strip()

    # Embed uses the SAME share URL + embed=true (+ theme)
    # NOTE: iframe can still be blocked by adblock/privacy; "Open Plausible" should always work.
    plausible_embed_url = _build_plausible_embed_url(plausible_shared_url, theme="light")

    plausible_period = (request.GET.get("period") or "30d").strip()
    allowed_periods = {"7d", "30d", "90d", "6mo", "12mo", "year", "today", "yesterday", "custom"}
    if plausible_period not in allowed_periods:
        plausible_period = "30d"

    selected_period = plausible_period
    api_period = plausible_period

    plausible_from = (request.GET.get("from") or "").strip()
    plausible_to = (request.GET.get("to") or "").strip()

    if selected_period in {"today", "yesterday"}:
        base_date = timezone.now().date()
        if selected_period == "yesterday":
            base_date = base_date - timedelta(days=1)
        plausible_from = base_date.isoformat()
        plausible_to = base_date.isoformat()
        api_period = "custom"
    elif selected_period != "custom":
        plausible_from = ""
        plausible_to = ""

    page_filter_raw = (request.GET.get("page") or "").strip()
    plausible_filters = ""
    if page_filter_raw:
        if page_filter_raw.startswith("="):
            value = page_filter_raw[1:].strip()
            if value:
                plausible_filters = f"event:page=={value}"
        else:
            value = re.escape(page_filter_raw)
            plausible_filters = f"event:page~={value}"

    try:
        plausible_top_limit = int(request.GET.get("limit") or 8)
    except ValueError:
        plausible_top_limit = 8
    plausible_top_limit = max(5, min(plausible_top_limit, 50))

    labels = {
        "7d": "Last 7 days",
        "30d": "Last 30 days",
        "90d": "Last 90 days",
        "6mo": "Last 6 months",
        "12mo": "Last 12 months",
        "year": "Year to date",
        "today": "Today",
        "yesterday": "Yesterday",
        "custom": "Custom range",
    }
    plausible_period_label = labels.get(selected_period, "Last 30 days")
    if plausible_period == "custom" and (plausible_from or plausible_to):
        if selected_period == "custom":
            plausible_period_label = f"{plausible_from or '…'} to {plausible_to or '…'}"

    plausible_api_enabled = plausible_is_configured()
    plausible_summary = {}
    plausible_top_pages = []
    plausible_summary_display = {}
    plausible_api_error = ""

    if plausible_api_enabled:
        try:
            if api_period == "custom" and not (plausible_from and plausible_to):
                plausible_api_error = "Select both From and To dates for a custom range."
                plausible_top_pages_raw = []
            else:
                plausible_summary = plausible_get_summary(
                    period=api_period,
                    from_date=plausible_from or None,
                    to_date=plausible_to or None,
                    filters=plausible_filters or None,
                )
                plausible_top_pages_raw = plausible_get_top_pages(
                    period=api_period,
                    limit=plausible_top_limit,
                    from_date=plausible_from or None,
                    to_date=plausible_to or None,
                    filters=plausible_filters or None,
                )

            def _safe_int(value, default=0):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            def _safe_float(value, default=0.0):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            def _format_duration(seconds):
                try:
                    total_seconds = int(float(seconds or 0))
                except (TypeError, ValueError):
                    total_seconds = 0

                mins, secs = divmod(total_seconds, 60)
                hours, mins = divmod(mins, 60)
                if hours:
                    return f"{hours}h {mins}m"
                if mins:
                    return f"{mins}m {secs}s"
                return f"{secs}s"

            plausible_summary_display = {
                "visitors": _safe_int(plausible_summary.get("visitors")),
                "pageviews": _safe_int(plausible_summary.get("pageviews")),
                "visits": _safe_int(plausible_summary.get("visits")),
                "bounce_rate": round(_safe_float(plausible_summary.get("bounce_rate")), 1),
                "visit_duration": _format_duration(plausible_summary.get("visit_duration")),
            }

            plausible_top_pages = []
            for row in plausible_top_pages_raw or []:
                plausible_top_pages.append(
                    {
                        "page": row.get("page") or row.get("name") or "",
                        "pageviews": _safe_int(row.get("pageviews")),
                        "visitors": _safe_int(row.get("visitors")),
                    }
                )
        except Exception as e:
            plausible_api_error = "Plausible API request failed."
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    detail = (resp.text or "").strip()
                    if detail:
                        plausible_api_error = f"Plausible API request failed ({resp.status_code}). {detail[:200]}"
                    else:
                        plausible_api_error = f"Plausible API request failed ({resp.status_code})."
                except Exception:
                    plausible_api_error = "Plausible API request failed."
            plausible_summary_display = {}
            plausible_top_pages = []

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
            "plausible_shared_url": plausible_shared_url,
            "plausible_embed_url": plausible_embed_url,
            "plausible_api_enabled": plausible_api_enabled,
            "plausible_summary": plausible_summary_display,
            "plausible_top_pages": plausible_top_pages,
            "plausible_period": plausible_period,
            "plausible_from": plausible_from,
            "plausible_to": plausible_to,
            "plausible_page_filter": page_filter_raw,
            "plausible_top_limit": plausible_top_limit,
            "plausible_period_label": plausible_period_label,
            "plausible_api_error": plausible_api_error,
        },
    )


@login_required
def admin_settings(request):
    user = request.user

    if not is_owner_user(user):
        messages.info(request, "You don’t have access to admin settings.")
        return redirect("dashboards:consumer")

    cfg = get_site_config()

    if request.method == "POST":
        form = SiteConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
            return redirect("dashboards:admin_settings")
    else:
        form = SiteConfigForm(instance=cfg)

    return render(
        request,
        "dashboards/admin_settings.html",
        {"form": form},
    )
