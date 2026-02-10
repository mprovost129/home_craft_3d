# refunds/models.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class RefundRequest(models.Model):
    """
    Refund requests are FULL refunds per PHYSICAL line item only (per locked spec).
    Digital products are never refundable in v1.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        REFUNDED = "refunded", "Refunded"
        CANCELED = "canceled", "Canceled"

    class Reason(models.TextChoices):
        DAMAGED = "damaged", "Item arrived damaged"
        NOT_AS_DESCRIBED = "not_as_described", "Not as described"
        LATE = "late", "Arrived too late"
        WRONG_ITEM = "wrong_item", "Wrong item received"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Denormalize for easier queries + integrity
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="refund_requests")
    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.CASCADE,
        related_name="refund_request",
        help_text="At most one refund request per order line item.",
    )

    # Snapshots for permission + display (do NOT depend on product->seller later)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="refund_requests_received",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refund_requests_made",
    )
    requester_email = models.EmailField(blank=True, default="")

    reason = models.CharField(max_length=32, choices=Reason.choices)
    notes = models.TextField(blank=True, default="")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)

    # Snapshot amounts at creation (FULL refund for this line item)
    line_subtotal_cents_snapshot = models.PositiveIntegerField(default=0)
    tax_cents_allocated_snapshot = models.PositiveIntegerField(default=0)
    shipping_cents_allocated_snapshot = models.PositiveIntegerField(default=0)
    total_refund_cents_snapshot = models.PositiveIntegerField(default=0)

    # Stripe refund tracking (partial refunds are allowed; we refund this line amount)
    stripe_refund_id = models.CharField(max_length=255, blank=True, default="")
    refunded_at = models.DateTimeField(null=True, blank=True)

    seller_decided_at = models.DateTimeField(null=True, blank=True)
    seller_decision_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["seller", "status", "-created_at"]),
            models.Index(fields=["buyer", "status", "-created_at"]),
            models.Index(fields=["order", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"RefundRequest<{self.pk}> {self.status}"

    def clean(self) -> None:
        super().clean()

        # Physical-only enforcement
        oi = self.order_item
        if oi.is_digital or not oi.requires_shipping:
            raise ValidationError("Refund requests are only allowed for physical items.")

        # Digital products are non-refundable
        try:
            if oi.product.kind == oi.product.Kind.FILE:
                raise ValidationError("Digital products are not refundable.")
        except Exception:
            # If product/kind isn't available for some reason, fail open here;
            # physical-guard above is still the hard gate.
            pass

        # Must be tied to the same order
        if oi.order_id != self.order_id:
            raise ValidationError("OrderItem must belong to the specified Order.")

    @property
    def is_decided(self) -> bool:
        return self.status in {
            self.Status.APPROVED,
            self.Status.DECLINED,
            self.Status.REFUNDED,
            self.Status.CANCELED,
        }

    @property
    def is_refundable_now(self) -> bool:
        return self.status == self.Status.APPROVED and not self.stripe_refund_id and not self.refunded_at




class RefundAttempt(models.Model):
    """Operational log for refund trigger attempts."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund_request = models.ForeignKey(RefundRequest, on_delete=models.CASCADE, related_name="attempts")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refund_attempts",
    )
    request_id = models.CharField(max_length=64, blank=True, default="")

    success = models.BooleanField(default=False)
    stripe_refund_id = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["success", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"RefundAttempt<{self.pk}> success={self.success}"


@dataclass(frozen=True)
class AllocatedLineRefund:
    line_subtotal_cents: int
    tax_cents_allocated: int
    shipping_cents_allocated: int
    total_refund_cents: int

    def as_dict(self) -> dict[str, int]:
        return {
            "line_subtotal_cents": int(self.line_subtotal_cents),
            "tax_cents_allocated": int(self.tax_cents_allocated),
            "shipping_cents_allocated": int(self.shipping_cents_allocated),
            "total_refund_cents": int(self.total_refund_cents),
        }
