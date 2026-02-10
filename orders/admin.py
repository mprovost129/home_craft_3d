# orders/admin.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.contrib import admin, messages
from django.db.models import (
    Sum,
    Count,
    Exists,
    OuterRef,
    Value,
    IntegerField,
    BooleanField,
    ExpressionWrapper,
    F,
    Case,
    When,
    Q,
)
from django.db.models.functions import Coalesce, Cast
from django.urls import reverse
from django.utils.html import format_html

from payments.models import SellerStripeAccount
from payments.services import get_seller_balance_cents

from .models import Order, OrderItem, OrderEvent, StripeWebhookEvent, StripeWebhookDelivery
from .stripe_service import create_transfers_for_paid_order

# IMPORTANT: must match the stored DB value (lowercase)
TRANSFER_EVENT_TYPE = OrderEvent.Type.TRANSFER_CREATED


# =========================
# Helpers
# =========================
def cents_to_money(cents: int | None, currency: str = "usd") -> str:
    if cents is None:
        cents = 0
    try:
        amount = int(cents) / 100.0
    except (TypeError, ValueError):
        amount = 0.0
    cur = (currency or "usd").upper()
    return f"{cur} {amount:,.2f}"


def admin_order_change_url(order_id) -> str:
    return reverse("admin:orders_order_change", args=[order_id])


# =========================
# Admin Filters
# =========================
class PaidStateFilter(admin.SimpleListFilter):
    title = "paid state"
    parameter_name = "paid_state"

    def lookups(self, request, model_admin):
        return (("paid", "Paid"), ("unpaid", "Unpaid"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "paid":
            return queryset.filter(paid_at__isnull=False)
        if val == "unpaid":
            return queryset.filter(paid_at__isnull=True)
        return queryset


class BuyerTypeFilter(admin.SimpleListFilter):
    title = "buyer type"
    parameter_name = "buyer_type"

    def lookups(self, request, model_admin):
        return (("user", "User account"), ("guest", "Guest checkout"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "user":
            return queryset.filter(buyer__isnull=False)
        if val == "guest":
            return queryset.filter(buyer__isnull=True).exclude(guest_email__exact="")
        return queryset


class FulfillmentMixFilter(admin.SimpleListFilter):
    title = "items"
    parameter_name = "mix"

    def lookups(self, request, model_admin):
        return (
            ("shipping", "Has shippable items"),
            ("digital", "Has digital items"),
            ("physical_only", "Physical-only"),
            ("digital_only", "Digital-only"),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val == "shipping":
            return queryset.filter(items__requires_shipping=True).distinct()
        if val == "digital":
            return queryset.filter(items__is_digital=True).distinct()
        if val == "physical_only":
            return queryset.filter(items__is_digital=False).distinct()
        if val == "digital_only":
            return (
                queryset.filter(items__is_digital=True)
                .exclude(items__is_digital=False)
                .distinct()
            )
        return queryset


class PayoutStateFilter(admin.SimpleListFilter):
    """
    Uses OrderEvent(type=transfer_created) as the authoritative "payout created" marker.
    """

    title = "payout state"
    parameter_name = "payout_state"

    def lookups(self, request, model_admin):
        return (
            ("unpaid", "Unpaid"),
            ("pending", "Paid, payout pending"),
            ("paid_out", "Paid out (transfer created)"),
            ("skipped_unready", "Payout skipped (seller not ready)"),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val == "unpaid":
            return queryset.filter(paid_at__isnull=True)
        if val == "pending":
            return queryset.filter(paid_at__isnull=False, has_transfer_event=False, payout_skipped_unready_seller=False)
        if val == "paid_out":
            return queryset.filter(paid_at__isnull=False, has_transfer_event=True)
        if val == "skipped_unready":
            return queryset.filter(paid_at__isnull=False, has_transfer_event=False, payout_skipped_unready_seller=True)
        return queryset


class ReconciliationFilter(admin.SimpleListFilter):
    """
    Flags that show "something is off" for production reconciliation.
    This relies on annotations done in OrderAdmin.get_queryset().
    """

    title = "reconciliation"
    parameter_name = "recon"

    def lookups(self, request, model_admin):
        return (
            ("ok", "OK"),
            ("totals_mismatch", "Totals mismatch (subtotal vs items gross)"),
            ("ledger_mismatch", "Ledger mismatch (expected fee/net vs stored)"),
            ("paid_missing_stripe", "Paid missing Stripe ids"),
            ("paid_missing_transfer", "Paid missing transfer event"),
            ("payout_skipped_unready", "Payout skipped (seller not ready)"),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val == "ok":
            return queryset.filter(
                totals_mismatch=False,
                ledger_mismatch=False,
                paid_missing_stripe_ids=False,
                paid_missing_transfer_event=False,
                payout_skipped_unready_seller=False,
            )
        if val == "totals_mismatch":
            return queryset.filter(totals_mismatch=True)
        if val == "ledger_mismatch":
            return queryset.filter(ledger_mismatch=True)
        if val == "paid_missing_stripe":
            return queryset.filter(paid_missing_stripe_ids=True)
        if val == "paid_missing_transfer":
            return queryset.filter(paid_missing_transfer_event=True)
        if val == "payout_skipped_unready":
            return queryset.filter(payout_skipped_unready_seller=True)
        return queryset


# =========================
# Inlines
# =========================
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = (
        "id",
        "product",
        "seller",
        "quantity",
        "unit_price_cents",
        "marketplace_fee_cents",
        "seller_net_cents",
        "is_digital",
        "requires_shipping",
        "created_at",
    )
    readonly_fields = fields
    show_change_link = True


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    can_delete = False
    fields = ("created_at", "type", "message")
    readonly_fields = ("created_at", "type", "message")
    ordering = ("-created_at",)
    show_change_link = True


# =========================
# Order Admin
# =========================
@dataclass(frozen=True)
class _SellerPayoutRow:
    seller_id: str
    seller_label: str
    connect_ready: bool
    gross_cents: int
    net_cents: int
    balance_cents: int
    payout_cents: int


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    inlines = [OrderItemInline, OrderEventInline]
    list_select_related = ("buyer",)

    list_display = (
        "id",
        "status",
        "kind",
        "currency",
        "buyer_display",
        "subtotal_money",
        "total_money",
        "items_gross_money",
        "expected_fee_money",
        "marketplace_fee_money",
        "expected_net_money",
        "seller_net_money",
        "items_qty",
        "seller_count",
        "paid_at",
        "payout_state_badge",
        "recon_badge",
        "created_at",
    )
    list_filter = (
        "status",
        "kind",
        "currency",
        PaidStateFilter,
        BuyerTypeFilter,
        FulfillmentMixFilter,
        PayoutStateFilter,
        ReconciliationFilter,
        "paid_at",
        "created_at",
    )
    search_fields = (
        "id",
        "guest_email",
        "stripe_session_id",
        "stripe_payment_intent_id",
        "buyer__username",
        "buyer__email",
    )
    raw_id_fields = ("buyer",)

    readonly_fields = (
        "id",
        "order_token",
        "created_at",
        "updated_at",
        "paid_at",
        "subtotal_cents",
        "tax_cents",
        "shipping_cents",
        "total_cents",
        "marketplace_sales_percent_snapshot",
        "platform_fee_cents_snapshot",  # legacy; must remain 0
        "payout_summary_html",
    )

    fieldsets = (
        ("Identity", {"fields": ("id", "status", "kind", "currency", "buyer", "guest_email", "order_token")}),
        ("Totals (cents)", {"fields": ("subtotal_cents", "tax_cents", "shipping_cents", "total_cents")}),
        ("Settings snapshots", {"fields": ("marketplace_sales_percent_snapshot", "platform_fee_cents_snapshot")}),
        ("Stripe", {"fields": ("stripe_session_id", "stripe_payment_intent_id", "paid_at")}),
        ("Payout summary", {"fields": ("payout_summary_html",)}),
        (
            "Shipping snapshot",
            {
                "fields": (
                    "shipping_name",
                    "shipping_phone",
                    "shipping_line1",
                    "shipping_line2",
                    "shipping_city",
                    "shipping_state",
                    "shipping_postal_code",
                    "shipping_country",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    actions = [
        "add_reconciliation_warning_event",
        "retry_payout_transfers",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # items gross: sum(quantity * unit_price_cents)
        line_total_expr = ExpressionWrapper(
            F("items__quantity") * F("items__unit_price_cents"),
            output_field=IntegerField(),
        )

        qs = qs.annotate(
            items_qty_agg=Coalesce(Sum("items__quantity"), Value(0), output_field=IntegerField()),
            seller_count_agg=Coalesce(Count("items__seller", distinct=True), Value(0), output_field=IntegerField()),
            items_gross_cents_agg=Coalesce(Sum(line_total_expr), Value(0), output_field=IntegerField()),
            marketplace_fee_cents_agg=Coalesce(Sum("items__marketplace_fee_cents"), Value(0), output_field=IntegerField()),
            seller_net_cents_agg=Coalesce(Sum("items__seller_net_cents"), Value(0), output_field=IntegerField()),
        )

        # transfer marker
        transfer_exists = OrderEvent.objects.filter(order_id=OuterRef("pk"), type=TRANSFER_EVENT_TYPE)
        qs = qs.annotate(has_transfer_event=Exists(transfer_exists))

        # payout skipped marker (from payout attempts)
        # stripe_service creates WARNING with message: "transfer skipped seller=... (not ready)"
        skipped_unready_exists = OrderEvent.objects.filter(
            order_id=OuterRef("pk"),
            type=OrderEvent.Type.WARNING,
            message__icontains="transfer skipped",
        ).filter(message__icontains="not ready")
        qs = qs.annotate(payout_skipped_unready_seller=Exists(skipped_unready_exists))

        # -------- Expected fee/net with exact ROUND_HALF_UP (percent-only) --------
        # marketplace_sales_percent_snapshot stored like 10.00 (Decimal)
        # Convert to integer basis points: 10.00% => 1000 bps (1 bps = 0.01%)
        # fee = round(gross * bps / 10000) => (gross*bps + 5000)//10000
        bps = Cast(F("marketplace_sales_percent_snapshot") * Value(100), IntegerField())

        expected_fee_cents = ExpressionWrapper(
            (F("items_gross_cents_agg") * bps + Value(5000)) / Value(10000),
            output_field=IntegerField(),
        )

        qs = qs.annotate(
            expected_fee_cents_agg=Coalesce(expected_fee_cents, Value(0), output_field=IntegerField()),
        ).annotate(
            expected_net_cents_agg=Coalesce(
                F("items_gross_cents_agg") - F("expected_fee_cents_agg"),
                Value(0),
                output_field=IntegerField(),
            ),
        )

        # flags
        qs = qs.annotate(
            totals_mismatch=Case(
                When(subtotal_cents=F("items_gross_cents_agg"), then=Value(False)),
                default=Value(True),
                output_field=BooleanField(),
            ),
            ledger_mismatch=Case(
                When(
                    marketplace_fee_cents_agg=F("expected_fee_cents_agg"),
                    seller_net_cents_agg=F("expected_net_cents_agg"),
                    then=Value(False),
                ),
                default=Value(True),
                output_field=BooleanField(),
            ),
        )

        # paid missing stripe ids (ignore FREE PI)
        qs = qs.annotate(
            paid_missing_stripe_ids=Case(
                When(paid_at__isnull=True, then=Value(False)),
                When(stripe_payment_intent_id__exact="FREE", then=Value(False)),
                When(stripe_session_id__exact="", then=Value(True)),
                When(stripe_payment_intent_id__exact="", then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            paid_missing_transfer_event=Case(
                When(paid_at__isnull=True, then=Value(False)),
                When(stripe_payment_intent_id__exact="FREE", then=Value(False)),
                When(has_transfer_event=True, then=Value(False)),
                # if skipped-unready, don't label as "missing transfer"; it's an explained state
                When(payout_skipped_unready_seller=True, then=Value(False)),
                default=Value(True),
                output_field=BooleanField(),
            ),
        )

        return qs

    # ---------------------
    # display helpers
    # ---------------------
    @admin.display(description="buyer")
    def buyer_display(self, obj: Order) -> str:
        if obj.buyer_id:
            return getattr(obj.buyer, "username", None) or getattr(obj.buyer, "email", "") or f"User<{obj.buyer_id}>"
        return obj.guest_email or "—"

    @admin.display(description="subtotal")
    def subtotal_money(self, obj: Order) -> str:
        return cents_to_money(obj.subtotal_cents, obj.currency)

    @admin.display(description="total")
    def total_money(self, obj: Order) -> str:
        return cents_to_money(obj.total_cents, obj.currency)

    @admin.display(description="items gross")
    def items_gross_money(self, obj: Order) -> str:
        return cents_to_money(int(getattr(obj, "items_gross_cents_agg", 0) or 0), obj.currency)

    @admin.display(description="exp fee")
    def expected_fee_money(self, obj: Order) -> str:
        return cents_to_money(int(getattr(obj, "expected_fee_cents_agg", 0) or 0), obj.currency)

    @admin.display(description="mkt fee (items)")
    def marketplace_fee_money(self, obj: Order) -> str:
        return cents_to_money(int(getattr(obj, "marketplace_fee_cents_agg", 0) or 0), obj.currency)

    @admin.display(description="exp net")
    def expected_net_money(self, obj: Order) -> str:
        return cents_to_money(int(getattr(obj, "expected_net_cents_agg", 0) or 0), obj.currency)

    @admin.display(description="seller net (items)")
    def seller_net_money(self, obj: Order) -> str:
        return cents_to_money(int(getattr(obj, "seller_net_cents_agg", 0) or 0), obj.currency)

    @admin.display(description="qty")
    def items_qty(self, obj: Order) -> int:
        return int(getattr(obj, "items_qty_agg", 0) or 0)

    @admin.display(description="sellers")
    def seller_count(self, obj: Order) -> int:
        return int(getattr(obj, "seller_count_agg", 0) or 0)

    @admin.display(description="payout")
    def payout_state_badge(self, obj: Order) -> str:
        if not obj.paid_at:
            return format_html("<span style='padding:2px 6px;border-radius:10px;background:#eee;'>UNPAID</span>")
        if getattr(obj, "has_transfer_event", False):
            return format_html("<span style='padding:2px 6px;border-radius:10px;background:#d1fae5;'>PAID OUT</span>")
        if getattr(obj, "payout_skipped_unready_seller", False):
            return format_html("<span style='padding:2px 6px;border-radius:10px;background:#fecaca;'>SKIPPED</span>")
        return format_html("<span style='padding:2px 6px;border-radius:10px;background:#fde68a;'>PENDING</span>")

    @admin.display(description="recon")
    def recon_badge(self, obj: Order) -> str:
        flags = []
        if getattr(obj, "totals_mismatch", False):
            flags.append("subtotal!=items")
        if getattr(obj, "ledger_mismatch", False):
            flags.append("fee/net!=expected")
        if getattr(obj, "paid_missing_stripe_ids", False):
            flags.append("paid missing stripe ids")
        if getattr(obj, "paid_missing_transfer_event", False):
            flags.append("paid missing transfer")
        if getattr(obj, "payout_skipped_unready_seller", False):
            flags.append("payout skipped (unready seller)")

        if not flags:
            return format_html("<span style='padding:2px 6px;border-radius:10px;background:#d1fae5;'>OK</span>")

        txt = "; ".join(flags)
        return format_html("<span style='padding:2px 6px;border-radius:10px;background:#fecaca;'>🚨 {}</span>", txt)

    # ---------------------
    # payout summary (order change view)
    # ---------------------
    @admin.display(description="Per-seller payout summary")
    def payout_summary_html(self, obj: Order) -> str:
        """
        Read-only operator view.
        We intentionally compute this live, because it’s for diagnostics/admin.
        (Order snapshots still protect the money math for payout creation.)
        """
        items = list(
            obj.items.select_related("seller").all()
        )
        if not items:
            return "—"

        # group by seller
        by_seller: dict[str, dict[str, Any]] = {}
        for it in items:
            sid = str(it.seller_id)
            if sid not in by_seller:
                label = getattr(it.seller, "username", "") or getattr(it.seller, "email", "") or sid
                by_seller[sid] = {
                    "seller": it.seller,
                    "label": label,
                    "gross": 0,
                    "net": 0,
                }

            gross = int(it.quantity) * int(it.unit_price_cents)
            by_seller[sid]["gross"] += max(0, gross)
            by_seller[sid]["net"] += max(0, int(it.seller_net_cents or 0))

        rows: list[_SellerPayoutRow] = []
        for sid, d in by_seller.items():
            seller = d["seller"]
            acct = SellerStripeAccount.objects.filter(user=seller).first()
            ready = bool(acct and acct.is_ready)
            bal = int(get_seller_balance_cents(seller=seller) or 0)
            payout = max(0, int(d["net"]) + bal)
            rows.append(
                _SellerPayoutRow(
                    seller_id=sid,
                    seller_label=str(d["label"]),
                    connect_ready=ready,
                    gross_cents=int(d["gross"]),
                    net_cents=int(d["net"]),
                    balance_cents=bal,
                    payout_cents=payout,
                )
            )

        rows.sort(key=lambda r: r.seller_label.lower())

        # render
        out = []
        out.append("<div style='max-width:980px'>")
        out.append("<table style='border-collapse:collapse;width:100%'>")
        out.append(
            "<thead><tr>"
            "<th style='text-align:left;border-bottom:1px solid #ddd;padding:6px'>Seller</th>"
            "<th style='text-align:left;border-bottom:1px solid #ddd;padding:6px'>Connect</th>"
            "<th style='text-align:right;border-bottom:1px solid #ddd;padding:6px'>Gross</th>"
            "<th style='text-align:right;border-bottom:1px solid #ddd;padding:6px'>Net</th>"
            "<th style='text-align:right;border-bottom:1px solid #ddd;padding:6px'>Balance</th>"
            "<th style='text-align:right;border-bottom:1px solid #ddd;padding:6px'>Payout (net+bal)</th>"
            "</tr></thead>"
        )
        out.append("<tbody>")
        for r in rows:
            badge = (
                "<span style='padding:2px 6px;border-radius:10px;background:#d1fae5'>READY</span>"
                if r.connect_ready
                else "<span style='padding:2px 6px;border-radius:10px;background:#fecaca'>NOT READY</span>"
            )
            out.append(
                "<tr>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2'>{r.seller_label}</td>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2'>{badge}</td>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2;text-align:right'>{cents_to_money(r.gross_cents, obj.currency)}</td>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2;text-align:right'>{cents_to_money(r.net_cents, obj.currency)}</td>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2;text-align:right'>{cents_to_money(r.balance_cents, obj.currency)}</td>"
                f"<td style='padding:6px;border-bottom:1px solid #f2f2f2;text-align:right'><b>{cents_to_money(r.payout_cents, obj.currency)}</b></td>"
                "</tr>"
            )
        out.append("</tbody></table>")

        if obj.paid_at and not obj.events.filter(type=OrderEvent.Type.TRANSFER_CREATED).exists():
            out.append(
                "<div style='margin-top:8px'>"
                "<b>Note:</b> Order is paid but no transfer_created event exists yet. "
                "Use the admin action <i>Retry payout transfers</i> if appropriate."
                "</div>"
            )

        out.append("</div>")
        return format_html("".join(out))

    # ---------------------
    # admin actions
    # ---------------------
    @admin.action(description="Add reconciliation WARNING event (non-destructive)")
    def add_reconciliation_warning_event(self, request, queryset):
        created = 0
        for o in queryset:
            flags = []
            if getattr(o, "totals_mismatch", False):
                flags.append(
                    f"subtotal({o.subtotal_cents}) != items_gross({getattr(o, 'items_gross_cents_agg', 0)})"
                )
            if getattr(o, "ledger_mismatch", False):
                flags.append(
                    f"items_fee({getattr(o, 'marketplace_fee_cents_agg', 0)})/items_net({getattr(o, 'seller_net_cents_agg', 0)}) "
                    f"!= expected_fee({getattr(o, 'expected_fee_cents_agg', 0)})/expected_net({getattr(o, 'expected_net_cents_agg', 0)})"
                )
            if getattr(o, "paid_missing_stripe_ids", False):
                flags.append("paid but missing stripe_session_id or stripe_payment_intent_id")
            if getattr(o, "paid_missing_transfer_event", False):
                flags.append("paid but missing transfer_created event")
            if getattr(o, "payout_skipped_unready_seller", False):
                flags.append("payout skipped because at least one seller not ready")

            if not flags:
                continue

            OrderEvent.objects.create(
                order=o,
                type=OrderEvent.Type.WARNING,
                message="ADMIN RECON: " + " | ".join(flags),
            )
            created += 1

        if created:
            self.message_user(request, f"Created {created} WARNING event(s).", level=messages.WARNING)
        else:
            self.message_user(request, "No reconciliation issues found in selection.", level=messages.INFO)

    @admin.action(description="Retry payout transfers (paid orders only)")
    def retry_payout_transfers(self, request, queryset):
        """
        Operator action:
          - Only applies to PAID orders with a real Stripe PI
          - Skips if transfer_created already exists
          - Writes OrderEvent warnings on problems (via stripe_service)
        """
        attempted = 0
        succeeded = 0
        skipped = 0

        for o in queryset.select_related("buyer"):
            if not o.paid_at or o.status != Order.Status.PAID:
                skipped += 1
                continue

            pi = (o.stripe_payment_intent_id or "").strip()
            if not pi or pi == "FREE":
                skipped += 1
                continue

            if o.events.filter(type=OrderEvent.Type.TRANSFER_CREATED).exists():
                skipped += 1
                continue

            attempted += 1
            try:
                create_transfers_for_paid_order(order=o, payment_intent_id=pi)
                # If a transfer was created, we'll have at least one event now.
                if o.events.filter(type=OrderEvent.Type.TRANSFER_CREATED).exists():
                    succeeded += 1
            except Exception:
                # Keep admin action resilient
                OrderEvent.objects.create(
                    order=o,
                    type=OrderEvent.Type.WARNING,
                    message="ADMIN: retry payout transfers failed (see server logs).",
                )

        if attempted == 0:
            self.message_user(request, "No eligible paid orders selected for payout retry.", level=messages.INFO)
            return

        self.message_user(
            request,
            f"Retry payouts: attempted={attempted}, succeeded={succeeded}, skipped={skipped}.",
            level=messages.SUCCESS if succeeded else messages.WARNING,
        )


# =========================
# Order Item Admin
# =========================
class OrderPaidFilter(admin.SimpleListFilter):
    title = "order paid"
    parameter_name = "order_paid"

    def lookups(self, request, model_admin):
        return (("paid", "Paid"), ("unpaid", "Unpaid"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "paid":
            return queryset.filter(order__paid_at__isnull=False)
        if val == "unpaid":
            return queryset.filter(order__paid_at__isnull=True)
        return queryset


class OrderPayoutFilter(admin.SimpleListFilter):
    title = "order payout"
    parameter_name = "order_payout"

    def lookups(self, request, model_admin):
        return (("pending", "Paid, payout pending"), ("paid_out", "Paid out (transfer created)"))

    def queryset(self, request, queryset):
        val = self.value()
        if val in {"pending", "paid_out"}:
            transfer_orders = OrderEvent.objects.filter(type=TRANSFER_EVENT_TYPE).values("order_id")
            if val == "paid_out":
                return queryset.filter(order_id__in=transfer_orders)
            return queryset.exclude(order_id__in=transfer_orders).filter(order__paid_at__isnull=False)
        return queryset


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_select_related = ("order", "product", "seller")

    list_display = (
        "id",
        "order_link",
        "order_status",
        "order_paid_at",
        "product",
        "seller",
        "quantity",
        "unit_price_money",
        "marketplace_fee_money",
        "seller_net_money",
        "is_digital",
        "requires_shipping",
        "created_at",
    )
    list_filter = (
        "is_digital",
        "requires_shipping",
        "created_at",
        "seller",
        "order__status",
        OrderPaidFilter,
        OrderPayoutFilter,
    )
    search_fields = (
        "id",
        "order__id",
        "product__title",
        "seller__username",
        "seller__email",
        "order__guest_email",
    )
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("order", "product", "seller")

    @admin.display(description="order", ordering="order__id")
    def order_link(self, obj: OrderItem):
        url = admin_order_change_url(obj.order_id)
        return format_html("<a href='{}'>#{}</a>", url, obj.order_id)

    @admin.display(description="order status", ordering="order__status")
    def order_status(self, obj: OrderItem) -> str:
        return str(obj.order.status)

    @admin.display(description="paid at", ordering="order__paid_at")
    def order_paid_at(self, obj: OrderItem):
        return obj.order.paid_at or "—"

    @admin.display(description="unit price")
    def unit_price_money(self, obj: OrderItem) -> str:
        return cents_to_money(obj.unit_price_cents, obj.order.currency)

    @admin.display(description="mkt fee")
    def marketplace_fee_money(self, obj: OrderItem) -> str:
        return cents_to_money(obj.marketplace_fee_cents, obj.order.currency)

    @admin.display(description="seller net")
    def seller_net_money(self, obj: OrderItem) -> str:
        return cents_to_money(obj.seller_net_cents, obj.order.currency)


# =========================
# Order Event Admin
# =========================
@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "order_link", "type", "message")
    list_filter = ("type", "created_at")
    search_fields = ("order__id", "message", "type")
    readonly_fields = ("id", "created_at", "order", "type", "message")
    list_select_related = ("order",)

    @admin.display(description="order", ordering="order__id")
    def order_link(self, obj: OrderEvent):
        url = admin_order_change_url(obj.order_id)
        return format_html("<a href='{}'>#{}</a>", url, obj.order_id)


# =========================
# Stripe Webhook Event Admin (idempotency audit)
# =========================

@admin.register(StripeWebhookDelivery)
class StripeWebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("received_at", "event_type", "status", "stripe_event_id", "request_id")
    list_filter = ("status", "event_type", "received_at")
    search_fields = ("stripe_event_id", "request_id", "event_type", "error_message")
    ordering = ("-received_at",)


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "event_type", "stripe_event_id")
    list_filter = ("event_type", "created_at")
    search_fields = ("stripe_event_id", "event_type")
    readonly_fields = ("id", "stripe_event_id", "event_type", "created_at")
    ordering = ("-created_at",)
