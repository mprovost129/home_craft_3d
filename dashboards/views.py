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
from django.templatetags.static import static
from django.utils.timezone import localdate
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
from refunds.models import RefundRequest
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

    # Use local time for analytics (America/New_York)
    from django.utils.timezone import localtime
    since = localtime(timezone.now()) - timedelta(days=DASH_RECENT_DAYS)

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
        eng = per_eng.get(p.id, {})
        views = int(eng.get(ProductEngagementEvent.EventType.VIEW, 0))
        clicks = int(eng.get(ProductEngagementEvent.EventType.CLICK, 0))
        adds = int(eng.get(ProductEngagementEvent.EventType.ADD_TO_CART, 0))
        paid_q = per_paid_qty.get(p.id, 0)
        ref_q = per_ref_qty.get(p.id, 0)
        net_sold = max(0, int(paid_q) - int(ref_q))

        dl_total = per_dl_total.get(p.id, 0)
        dl_unique = per_dl_user_unique.get(p.id, 0) + per_dl_sess_unique.get(p.id, 0)

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
        "gross_dollars": _cents_to_dollars(int(paid_totals["gross_cents"] or 0)),
        "net_dollars": _cents_to_dollars(int(paid_totals["net_cents"] or 0)),
        "order_count": int(paid_totals["order_count"] or 0),
        "rows": per_rows,
    }
    return render(request, "dashboards/seller_analytics.html", context)



def admin_dashboard(request):
    user = request.user

    if not is_owner_user(user):
        messages.info(request, "You don’t have access to the admin dashboard.")
        return redirect("dashboards:consumer")

    # Use local time for analytics (America/New_York)
    from django.utils.timezone import localtime
    since = localtime(timezone.now()) - timedelta(days=DASH_RECENT_DAYS)

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

    plausible_period = (request.GET.get("period") or "today").strip()
    allowed_periods = {"7d", "30d", "90d", "6mo", "12mo", "year", "today", "yesterday", "custom"}
    if plausible_period not in allowed_periods:
        plausible_period = "30d"

    selected_period = plausible_period
    api_period = plausible_period

    plausible_from = (request.GET.get("from") or "").strip()
    plausible_to = (request.GET.get("to") or "").strip()

    if selected_period in {"today", "yesterday"}:
        # Use local time for analytics (America/New_York)
        from django.utils.timezone import localtime
        base_date = localtime(timezone.now()).date()
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
def ajax_verify_username(request):
    """AJAX endpoint to verify username and return email if user exists."""
    username = request.GET.get("username", "").strip()
    User = get_user_model()
    try:
        user = User.objects.get(username=username, is_active=True)
        return JsonResponse({"success": True, "email": user.email})
    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "No active user found with this username."})
