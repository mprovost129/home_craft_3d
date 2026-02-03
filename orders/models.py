# orders/models.py

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models
from django.urls import reverse
from django.utils import timezone


def _site_base_url() -> str:
    """
    Absolute base URL used in emails for guest access/download links.
    Set SITE_BASE_URL in env (recommended), e.g. https://homecraft3d.com
    """
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip().rstrip("/")
    if base:
        return base
    return "http://localhost:8000"


def _send_guest_paid_email_with_downloads(order: "Order") -> None:
    """
    Send guest email containing:
      - order detail link (tokenized)
      - digital asset download links (tokenized), if any
    """
    if not order.guest_email:
        return

    base = _site_base_url()
    order_link = f"{base}{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}"

    product_ids = list(order.items.values_list("product_id", flat=True))
    if not product_ids:
        assets = []
    else:
        from products.models import DigitalAsset  # noqa

        assets = list(
            DigitalAsset.objects.filter(product_id__in=product_ids)
            .select_related("product")
            .order_by("product_id", "id")
        )

    lines: list[str] = []
    lines.append("Thanks for your purchase at Home Craft 3D!")
    lines.append("")
    lines.append("Access your order here:")
    lines.append(order_link)
    lines.append("")

    if assets:
        lines.append("Your digital downloads (links are tied to your order):")
        for a in assets:
            try:
                if a.product.kind != a.product.Kind.FILE:
                    continue
            except Exception:
                continue

            fn = a.original_filename or (a.file.name.rsplit("/", 1)[-1] if a.file else "download")
            dl = (
                f"{base}"
                f"{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
                f"?t={order.order_token}"
            )
            lines.append(f"- {fn}: {dl}")
        lines.append("")

    lines.append("If you didn’t make this purchase, you can ignore this email.")

    subject = f"Your Home Craft 3D order #{order.pk}"
    body = "\n".join(lines)

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [order.guest_email],
        )
    except Exception:
        pass


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        REFUNDED = "refunded", "Refunded"

    class Kind(models.TextChoices):
        DIGITAL = "digital", "Digital only"
        PHYSICAL = "physical", "Physical only"
        MIXED = "mixed", "Mixed (digital + physical)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Registered buyer. Null means guest checkout.",
    )
    guest_email = models.EmailField(blank=True, default="")

    order_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PHYSICAL)

    currency = models.CharField(max_length=8, default="usd")

    subtotal_cents = models.PositiveIntegerField(default=0)
    tax_cents = models.PositiveIntegerField(default=0)
    shipping_cents = models.PositiveIntegerField(default=0)
    total_cents = models.PositiveIntegerField(default=0)

    # Snapshot settings (historical correctness)
    marketplace_sales_percent_snapshot = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Marketplace % cut captured at order creation time.",
    )

    # Legacy field: kept for compatibility, but MUST be 0 (platform fee not used).
    platform_fee_cents_snapshot = models.PositiveIntegerField(
        default=0,
        help_text="Legacy flat fee snapshot (NOT USED). Keep at 0.",
    )

    stripe_session_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")

    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    shipping_name = models.CharField(max_length=255, blank=True, default="")
    shipping_phone = models.CharField(max_length=64, blank=True, default="")
    shipping_line1 = models.CharField(max_length=255, blank=True, default="")
    shipping_line2 = models.CharField(max_length=255, blank=True, default="")
    shipping_city = models.CharField(max_length=120, blank=True, default="")
    shipping_state = models.CharField(max_length=120, blank=True, default="")
    shipping_postal_code = models.CharField(max_length=32, blank=True, default="")
    shipping_country = models.CharField(max_length=2, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["kind", "-created_at"]),
            models.Index(fields=["-paid_at"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.pk} ({self.status})"

    @property
    def access_token(self) -> uuid.UUID:
        return self.order_token

    def ensure_access_token(self) -> None:
        if not self.order_token:
            self.order_token = uuid.uuid4()
            self.save(update_fields=["order_token", "updated_at"])

    def clean(self) -> None:
        has_buyer = bool(self.buyer_id)
        has_guest = bool((self.guest_email or "").strip())
        if not has_buyer and not has_guest:
            raise ValidationError("Order must have either a buyer or a guest_email.")
        if has_buyer and has_guest:
            self.guest_email = ""
        super().clean()

    @property
    def is_guest(self) -> bool:
        return self.buyer_id is None

    @property
    def requires_shipping(self) -> bool:
        return self.items.filter(requires_shipping=True).exists()

    def recompute_totals(self) -> None:
        subtotal = 0
        any_digital = False
        any_physical = False

        for oi in self.items.all():
            subtotal += int(oi.line_total_cents)
            if oi.is_digital:
                any_digital = True
            if oi.requires_shipping:
                any_physical = True

        self.subtotal_cents = int(subtotal)
        self.total_cents = int(self.subtotal_cents + self.tax_cents + self.shipping_cents)

        if any_digital and any_physical:
            self.kind = self.Kind.MIXED
        elif any_digital:
            self.kind = self.Kind.DIGITAL
        else:
            self.kind = self.Kind.PHYSICAL

    def set_shipping_from_stripe(
        self,
        *args,
        name: str = "",
        phone: str = "",
        line1: str = "",
        line2: str = "",
        city: str = "",
        state: str = "",
        postal_code: str = "",
        country: str = "",
    ) -> None:
        self.shipping_name = name or ""
        self.shipping_phone = phone or ""
        self.shipping_line1 = line1 or ""
        self.shipping_line2 = line2 or ""
        self.shipping_city = city or ""
        self.shipping_state = state or ""
        self.shipping_postal_code = postal_code or ""
        self.shipping_country = country or ""
        self.save(
            update_fields=[
                "shipping_name",
                "shipping_phone",
                "shipping_line1",
                "shipping_line2",
                "shipping_city",
                "shipping_state",
                "shipping_postal_code",
                "shipping_country",
                "updated_at",
            ]
        )

    def _add_event(self, type_: str, message: str = "") -> None:
        try:
            OrderEvent.objects.create(order=self, type=type_, message=message or "")
        except Exception:
            pass

    def mark_paid(
        self,
        *,
        payment_intent_id: str = "",
        session_id: str = "",
        paid_at: Optional[timezone.datetime] = None,
        note: str = "",
    ) -> bool:
        changed = False
        now = paid_at or timezone.now()

        update_fields: list[str] = []

        payment_intent_id = (payment_intent_id or "").strip()
        session_id = (session_id or "").strip()

        if session_id and not self.stripe_session_id:
            self.stripe_session_id = session_id
            update_fields.append("stripe_session_id")

        if payment_intent_id and not self.stripe_payment_intent_id:
            self.stripe_payment_intent_id = payment_intent_id
            update_fields.append("stripe_payment_intent_id")

        if self.status != self.Status.PAID:
            self.status = self.Status.PAID
            update_fields.append("status")
            changed = True

        if not self.paid_at:
            self.paid_at = now
            update_fields.append("paid_at")
            changed = True

        if update_fields:
            update_fields.append("updated_at")
            self.save(update_fields=update_fields)

        if changed:
            msg = note or ""
            if payment_intent_id and payment_intent_id != "FREE":
                msg = msg or f"Marked paid via Stripe PI {payment_intent_id}"
            elif payment_intent_id == "FREE":
                msg = msg or "Marked paid via FREE checkout"
            self._add_event(OrderEvent.Type.PAID, msg)

            if self.is_guest and (self.guest_email or "").strip():
                _send_guest_paid_email_with_downloads(self)

        return changed


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sold_order_items",
        help_text="Seller snapshot at time of purchase.",
    )

    quantity = models.PositiveIntegerField(default=1)
    unit_price_cents = models.PositiveIntegerField(default=0)

    is_digital = models.BooleanField(default=False)
    requires_shipping = models.BooleanField(default=True)

    marketplace_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="Marketplace fee on this line (percent-based).",
    )
    seller_net_cents = models.PositiveIntegerField(
        default=0,
        help_text="Seller net on this line (gross - marketplace_fee).",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["order", "created_at"]),
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["seller", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_id}"

    @property
    def line_total_cents(self) -> int:
        return int(self.quantity) * int(self.unit_price_cents)


LineItem = OrderItem


class OrderEvent(models.Model):
    class Type(models.TextChoices):
        CREATED = "created", "Created"
        STRIPE_SESSION_CREATED = "stripe_session_created", "Stripe session created"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        REFUNDED = "refunded", "Refunded"
        TRANSFER_CREATED = "transfer_created", "Transfer created"
        WARNING = "warning", "Warning"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=64, choices=Type.choices)
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["order", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.type} ({self.created_at:%Y-%m-%d %H:%M})"


class StripeWebhookEvent(models.Model):
    """
    Records processed Stripe webhook events for strict idempotency.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_event_id"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.stripe_event_id})"
