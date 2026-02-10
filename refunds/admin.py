# refunds/admin.py

from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .models import RefundRequest, RefundAttempt


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "reason",
        "order_link",
        "order_item_link",
        "seller",
        "buyer_or_guest",
        "total_refund_display",
        "created_at",
    )
    list_filter = ("status", "reason", "created_at", "seller")
    search_fields = (
        "id",
        "order__id",
        "order_item__id",
        "seller__username",
        "buyer__username",
        "requester_email",
        "stripe_refund_id",
    )
    ordering = ("-created_at",)
    actions = ("admin_trigger_refund",)

    readonly_fields = (
        "id",
        "order",
        "order_item",
        "seller",
        "buyer",
        "requester_email",
        "reason",
        "notes",
        "status",
        "line_subtotal_cents_snapshot",
        "tax_cents_allocated_snapshot",
        "shipping_cents_allocated_snapshot",
        "total_refund_cents_snapshot",
        "stripe_refund_id",
        "refunded_at",
        "seller_decided_at",
        "seller_decision_note",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identity", {"fields": ("id", "status", "reason", "created_at", "updated_at")}),
        ("Parties", {"fields": ("order", "order_item", "seller", "buyer", "requester_email")}),
        ("Buyer request", {"fields": ("notes",)}),
        (
            "Snapshots (source of truth)",
            {
                "fields": (
                    "line_subtotal_cents_snapshot",
                    "tax_cents_allocated_snapshot",
                    "shipping_cents_allocated_snapshot",
                    "total_refund_cents_snapshot",
                )
            },
        ),
        ("Seller decision", {"fields": ("seller_decided_at", "seller_decision_note")}),
        ("Stripe", {"fields": ("stripe_refund_id", "refunded_at")}),
    )

    def order_link(self, obj: RefundRequest) -> str:
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order_id)

    order_link.short_description = "Order"

    def order_item_link(self, obj: RefundRequest) -> str:
        url = reverse("admin:orders_orderitem_change", args=[obj.order_item_id])
        return format_html('<a href="{}">{}</a>', url, obj.order_item_id)

    order_item_link.short_description = "Order item"

    def buyer_or_guest(self, obj: RefundRequest) -> str:
        if obj.buyer_id:
            return getattr(obj.buyer, "username", str(obj.buyer_id))
        return f"Guest ({(obj.requester_email or '').strip()})"

    buyer_or_guest.short_description = "Buyer"

    def total_refund_display(self, obj: RefundRequest) -> str:
        cents = int(obj.total_refund_cents_snapshot or 0)
        return f"${cents / 100:.2f}"

    total_refund_display.short_description = "Refund total"

    @admin.action(description="Trigger Stripe refund (DANGEROUS) for APPROVED requests")
    def admin_trigger_refund(self, request, queryset):
        """
        Safety valve:
        - Only APPROVED, not already refunded
        - Uses service layer so invariants stay centralized
        """
        from .services import trigger_refund  # local import

        count_ok = 0
        count_skip = 0

        for rr in queryset.select_related("order", "seller"):
            if rr.status != RefundRequest.Status.APPROVED or rr.stripe_refund_id or rr.refunded_at:
                count_skip += 1
                continue

            try:
                trigger_refund(rr=rr, actor_user=request.user, allow_staff_safety_valve=True)
                count_ok += 1
            except Exception as e:
                count_skip += 1
                messages.error(request, f"Refund {rr.pk}: {e}")

        if count_ok:
            messages.success(request, f"Processed {count_ok} refund(s).")
        if count_skip:
            messages.info(request, f"Skipped {count_skip} refund(s).")


@admin.register(RefundAttempt)
class RefundAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "refund_request", "actor", "stripe_refund_id")
    list_filter = ("status", "created_at")
    search_fields = ("refund_request__id", "stripe_refund_id", "actor__username", "error_message", "request_id")
    ordering = ("-created_at",)
