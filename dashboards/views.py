# dashboards/views.py

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, IntegerField, Sum
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from core.config import get_site_config
from .forms import SiteConfigForm
from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount, SellerBalanceEntry
from products.models import Product
from products.permissions import is_owner_user, is_seller_user
from payments.services import get_seller_balance_cents


DASH_RECENT_DAYS = 30


def _cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(int(cents or 0)) / Decimal("100")).quantize(Decimal("0.01"))


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

    payout_available_cents = max(
        0, int((sales_totals.get("net_cents") or 0) + balance_cents)
    )

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

    # ---- Plausible (shared dashboard link) ----
    plausible_shared_url = (getattr(cfg, "plausible_shared_url", "") or "").strip()
    plausible_embed_url = plausible_shared_url.replace("/share/", "/embed/") if plausible_shared_url else ""

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
