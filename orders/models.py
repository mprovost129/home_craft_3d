from __future__ import annotations

from decimal import Decimal
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_order_access_token() -> str:
    return secrets.token_urlsafe(32)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FULFILLED = "FULFILLED", "Fulfilled"
        CANCELED = "CANCELED", "Canceled"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Null if guest checkout (MVP).",
    )

    # Guest checkout identity (email only for MVP)
    guest_email = models.EmailField(blank=True, default="")

    # Magic-link token for guest order access
    access_token = models.CharField(max_length=128, blank=True, default="", db_index=True)
    access_token_created_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    currency = models.CharField(max_length=8, default="USD")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # Stripe tracking (MVP)
    stripe_session_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)

    # Shipping address (for physical MODEL items)
    ship_name = models.CharField(max_length=120, blank=True, default="")
    ship_phone = models.CharField(max_length=40, blank=True, default="")
    ship_line1 = models.CharField(max_length=200, blank=True, default="")
    ship_line2 = models.CharField(max_length=200, blank=True, default="")
    ship_city = models.CharField(max_length=120, blank=True, default="")
    ship_state = models.CharField(max_length=80, blank=True, default="")
    ship_postal_code = models.CharField(max_length=20, blank=True, default="")
    ship_country = models.CharField(max_length=2, blank=True, default="")  # US, etc.

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.status})"

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def is_guest(self) -> bool:
        return self.buyer_id is None

    def ensure_access_token(self) -> None:
        if not self.access_token:
            self.access_token = generate_order_access_token()
            self.access_token_created_at = timezone.now()
            self.save(update_fields=["access_token", "access_token_created_at", "updated_at"])

    def mark_paid(self, *, payment_intent_id: str = "") -> None:
        if self.status == self.Status.PAID:
            return
        self.status = self.Status.PAID
        if payment_intent_id and not self.stripe_payment_intent_id:
            self.stripe_payment_intent_id = payment_intent_id
        if not self.paid_at:
            self.paid_at = timezone.now()
        self.save(update_fields=["status", "stripe_payment_intent_id", "paid_at", "updated_at"])

    def set_shipping_from_stripe(
        self,
        *,
        name: str = "",
        phone: str = "",
        line1: str = "",
        line2: str = "",
        city: str = "",
        state: str = "",
        postal_code: str = "",
        country: str = "",
    ) -> None:
        self.ship_name = (name or "").strip()
        self.ship_phone = (phone or "").strip()
        self.ship_line1 = (line1 or "").strip()
        self.ship_line2 = (line2 or "").strip()
        self.ship_city = (city or "").strip()
        self.ship_state = (state or "").strip()
        self.ship_postal_code = (postal_code or "").strip()
        self.ship_country = (country or "").strip()
        self.save(
            update_fields=[
                "ship_name",
                "ship_phone",
                "ship_line1",
                "ship_line2",
                "ship_city",
                "ship_state",
                "ship_postal_code",
                "ship_country",
                "updated_at",
            ]
        )


class OrderItem(models.Model):
    """
    Snapshot of the product at purchase time + per-seller fulfillment state.
    """
    class FulfillmentStatus(models.TextChoices):
        UNFULFILLED = "UNFULFILLED", "Unfulfilled"
        SHIPPED = "SHIPPED", "Shipped"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sold_items",
        help_text="Seller at time of purchase.",
    )

    kind = models.CharField(max_length=10)  # MODEL / FILE
    title = models.CharField(max_length=160)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    quantity = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # Fulfillment (per seller line item)
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
    )
    shipped_at = models.DateTimeField(null=True, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True, default="")
    carrier = models.CharField(max_length=40, blank=True, default="")  # placeholder

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Item<{self.order_id}> {self.title} x{self.quantity}"

    @property
    def is_digital(self) -> bool:
        return self.kind == "FILE"

    def mark_shipped(self, *, tracking_number: str = "", carrier: str = "") -> None:
        self.fulfillment_status = self.FulfillmentStatus.SHIPPED
        self.shipped_at = timezone.now()
        self.tracking_number = (tracking_number or "").strip()
        self.carrier = (carrier or "").strip()
        self.save(update_fields=["fulfillment_status", "shipped_at", "tracking_number", "carrier"])
