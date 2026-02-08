# dashboards/views.py

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re

from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, IntegerField, Sum
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.config import get_site_config, invalidate_site_config_cache
from core.models import SiteConfig
from .forms import SiteConfigForm, ProductFreeUnlockForm
from .plausible import get_summary as plausible_get_summary
from .plausible import get_top_pages as plausible_get_top_pages
from .plausible import is_configured as plausible_is_configured
from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount, SellerBalanceEntry
from products.models import Product
from products.permissions import is_owner_user, is_seller_user
from payments.services import get_seller_balance_cents


DASH_RECENT_DAYS = 30

# Keep in sync with core.views
HOME_ANON_CACHE_KEY = "home_html_anon_v2"


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

    def _parse_url_and_query(url):
        parsed = urlparse(url)
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        return parsed, qs

    try:
        parsed, qs = _parse_url_and_query(shared_url)
        qs["embed"] = "true"
        if theme:
            qs["theme"] = theme
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
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

    since = timezone.now() - timedelta(days=DASH_RECENT_DAYS)

    stripe_obj, _ = SellerStripeAccount.objects.get_or_create(user=user)
    balance_cents = get_seller_balance_cents(seller=user)

    listings_total = Product.objects.filter(seller=user, is_active=True).count()
    listings_inactive = Product.objects.filter(seller=user, is_active=False).count()

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
    )

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
                    product = grant_form.cleaned_data["product"]
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
            "sold_count": sales_totals.get("sold_count") or 0,
            "order_count": sales_totals.get("order_count") or 0,
            "since_days": DASH_RECENT_DAYS,
            "grant_form": grant_form,
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

    plausible_shared_url = (getattr(cfg, "plausible_shared_url", "") or "").strip()
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
    if plausible_period == "custom" and selected_period == "custom" and (plausible_from or plausible_to):
        plausible_period_label = f"{plausible_from or '…'} to {plausible_to or '…'}"

    plausible_api_enabled = plausible_is_configured()
    plausible_summary_display = {}
    plausible_top_pages = []
    plausible_api_error = ""

    if plausible_api_enabled:
        try:
            if api_period == "custom" and not (plausible_from and plausible_to):
                plausible_api_error = "Select both From and To dates for a custom range."
                plausible_top_pages_raw = []
                plausible_summary = {}
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
                    if isinstance(value, dict) and "value" in value:
                        value = value.get("value")
                    return int(value)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return default

            def _safe_float(value, default=0.0):
                try:
                    if isinstance(value, dict) and "value" in value:
                        value = value.get("value")
                    return float(value)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return default

            def _format_duration(seconds):
                try:
                    if isinstance(seconds, dict) and "value" in seconds:
                        seconds = seconds.get("value")
                    total_seconds = int(float(seconds or 0))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    total_seconds = 0

                mins, secs = divmod(total_seconds, 60)
                hours, mins = divmod(mins, 60)
                if hours:
                    return f"{hours}h {mins}m"
                else:
                    return f"{mins}m {secs}s" if mins else f"{secs}s"

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
            try:
                invalidate_site_config_cache()
            except Exception:
                pass
            try:
                cache.delete(HOME_ANON_CACHE_KEY)
            except Exception:
                pass

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
def ajax_verify_username(request):
    """AJAX endpoint to verify username and return email if user exists."""
    username = request.GET.get("username", "").strip()
    User = get_user_model()
    try:
        user = User.objects.get(username=username, is_active=True)
        return JsonResponse({"success": True, "email": user.email})
    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "No active user found with this username."})
