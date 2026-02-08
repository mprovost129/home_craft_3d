# orders/models.py

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
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


def _absolute_static_url(path: str) -> str:
    base = _site_base_url().rstrip("/")
    static_url = (getattr(settings, "STATIC_URL", "/static/") or "/static/").strip()
    if not static_url.startswith("/"):
        static_url = f"/{static_url}"
    if not static_url.endswith("/"):
        static_url = f"{static_url}/"
    return f"{base}{static_url}{path.lstrip('/')}"


def _order_detail_link(*, order: "Order", base: str) -> str:
    link = f"{base}{reverse('orders:detail', kwargs={'order_id': order.pk})}"
    if order.is_guest:
        link = f"{link}?t={order.order_token}"
    return link


def _get_order_recipient_email(order: "Order") -> str:
    if order.buyer and order.buyer.email:
        return order.buyer.email
    if order.guest_email:
        return order.guest_email
    return ""


def _send_order_canceled_email(order: "Order") -> None:
    recipient_email = _get_order_recipient_email(order)
    if not recipient_email:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _order_detail_link(order=order, base=base)

    subject = f"Your Home Craft 3D order #{order.pk} was canceled"
    body = "\n".join(
        [
            f"Your order #{order.pk} was canceled.",
            "",
            "View order details:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/order_canceled.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient_email],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_order_failed_email(order: "Order", reason: str = "") -> None:
    recipient_email = _get_order_recipient_email(order)
    if not recipient_email:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _order_detail_link(order=order, base=base)
    reason = (reason or "Payment failed.").strip()

    subject = f"Payment failed for order #{order.pk}"
    body = "\n".join(
        [
            f"We couldn't process payment for order #{order.pk}.",
            reason,
            "",
            "View order details:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/order_failed.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
            "reason": reason,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient_email],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_payout_email(
    *,
    order: "Order",
    seller,
    payout_cents: int,
    balance_before_cents: int,
    transfer_id: str,
) -> None:
    if not seller or not getattr(seller, "email", None):
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = f"{base}{reverse('orders:seller_order_detail', kwargs={'order_id': order.pk})}"

    payout_amount = float(payout_cents) / 100.0
    balance_before = float(balance_before_cents) / 100.0

    subject = f"Transfer sent for order #{order.pk}"
    body = "\n".join(
        [
            f"A transfer was sent for order #{order.pk}.",
            f"Amount: ${payout_amount:.2f}",
            f"Balance before payout: ${balance_before:.2f}",
            "",
            "View order details:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/payout_sent.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
            "payout_amount": f"${payout_amount:.2f}",
            "balance_before": f"${balance_before:.2f}",
            "transfer_id": transfer_id,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [seller.email],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_download_reminder_email(order: "Order") -> bool:
    recipient_email = _get_order_recipient_email(order)
    if not recipient_email:
        return False

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _order_detail_link(order=order, base=base)

    # IMPORTANT: exclude tip lines
    product_ids = list(order.items.filter(is_tip=False).values_list("product_id", flat=True))
    if not product_ids:
        assets = []
    else:
        from products.models import DigitalAsset  # noqa

        assets = list(
            DigitalAsset.objects.filter(product_id__in=product_ids)
            .select_related("product")
            .order_by("product_id", "id")
        )

    downloads = []
    for a in assets:
        try:
            if a.product.kind != a.product.Kind.FILE:
                continue
        except Exception:
            continue

        fn = a.original_filename or (a.file.name.rsplit("/", 1)[-1] if a.file else "download")
        if order.is_guest:
            dl = (
                f"{base}"
                f"{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
                f"?t={order.order_token}"
            )
        else:
            dl = f"{base}{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
        downloads.append({"filename": fn, "url": dl})

    if not downloads:
        return False

    subject = f"Your Home Craft 3D downloads are ready (Order #{order.pk})"
    body = "\n".join(
        [
            f"Your downloads for order #{order.pk} are ready.",
            "",
            "Access your order:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/download_reminder.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
            "downloads": downloads,
            "is_guest": bool(order.is_guest),
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient_email],
            html_message=html_message,
        )
        return True
    except Exception:
        return False


def _send_review_request_email(order: "Order", item: "OrderItem") -> None:
    if not order.buyer or not order.buyer.email:
        return
    if item.is_tip:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    review_link = f"{base}{reverse('reviews:review_for_item', kwargs={'order_item_id': item.pk})}"

    subject = f"How was your order? Review {item.product.title}"
    body = "\n".join(
        [
            f"Thanks for your purchase! We'd love your review for {item.product.title}.",
            "",
            "Leave a review:",
            review_link,
        ]
    )

    html_message = render_to_string(
        "emails/review_request.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "product_title": item.product.title,
            "review_link": review_link,
            "order_id": order.pk,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [order.buyer.email],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_paid_order_email(order: "Order") -> None:
    """
    Send order confirmation email to buyer (authenticated or guest).
    For guests: includes tokenized links for order access and downloads.
    For authenticated: includes direct links to purchases page.
    """
    recipient_email = ""
    if order.buyer and order.buyer.email:
        recipient_email = order.buyer.email
    elif order.guest_email:
        recipient_email = order.guest_email

    if not recipient_email:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")

    if order.is_guest:
        order_link = f"{base}{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}"
    else:
        order_link = f"{base}{reverse('orders:purchases')}"

    # IMPORTANT: exclude tip lines
    product_ids = list(order.items.filter(is_tip=False).values_list("product_id", flat=True))
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

    if order.is_guest:
        lines.append("Access your order here:")
    else:
        lines.append("View your order in your purchases:")
    lines.append(order_link)
    lines.append("")

    if assets:
        if order.is_guest:
            lines.append("Your digital downloads (links are tied to your order):")
        else:
            lines.append("Your digital downloads:")
        for a in assets:
            try:
                if a.product.kind != a.product.Kind.FILE:
                    continue
            except Exception:
                continue

            fn = a.original_filename or (a.file.name.rsplit("/", 1)[-1] if a.file else "download")

            if order.is_guest:
                dl = (
                    f"{base}"
                    f"{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
                    f"?t={order.order_token}"
                )
            else:
                dl = f"{base}{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
            lines.append(f"- {fn}: {dl}")
        lines.append("")

    if order.is_guest:
        lines.append("If you didn't make this purchase, you can ignore this email.")

    subject = f"Your Home Craft 3D order #{order.pk}"
    body = "\n".join(lines)

    downloads = []
    for a in assets:
        try:
            if a.product.kind != a.product.Kind.FILE:
                continue
        except Exception:
            continue

        fn = a.original_filename or (a.file.name.rsplit("/", 1)[-1] if a.file else "download")
        if order.is_guest:
            dl = (
                f"{base}"
                f"{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
                f"?t={order.order_token}"
            )
        else:
            dl = f"{base}{reverse('orders:download_asset', kwargs={'order_id': order.pk, 'asset_id': a.pk})}"
        downloads.append({"filename": fn, "url": dl})

    html_message = render_to_string(
        "emails/order_paid.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
            "downloads": downloads,
            "is_guest": bool(order.is_guest),
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient_email],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_seller_new_order_email(order: "Order") -> None:
    """
    Send notification to sellers when they receive paid orders with physical items.
    IMPORTANT: excludes tip lines.
    """
    sellers_with_physical = {}
    for item in order.items.filter(requires_shipping=True, is_tip=False).select_related("seller"):
        seller = item.seller
        if seller and seller.email:
            if seller.id not in sellers_with_physical:
                sellers_with_physical[seller.id] = {
                    "seller": seller,
                    "items": [],
                }
            sellers_with_physical[seller.id]["items"].append(item)

    if not sellers_with_physical:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    fulfillment_link = f"{base}{reverse('orders:seller_order_detail', kwargs={'order_id': order.pk})}"

    for seller_info in sellers_with_physical.values():
        seller = seller_info["seller"]
        items = seller_info["items"]

        lines: list[str] = []
        lines.append(f"New order received! Order #{order.pk}")
        lines.append("")
        lines.append("View and fulfill this order:")
        lines.append(fulfillment_link)
        lines.append("")
        lines.append("Items to ship:")
        for item in items:
            lines.append(f"- {item.quantity}x {item.product.title} (${item.line_total_cents / 100:.2f})")
        lines.append("")

        if order.requires_shipping:
            lines.append("Shipping address:")
            lines.append(f"{order.shipping_name}")
            if order.shipping_line1:
                lines.append(f"{order.shipping_line1}")
                if order.shipping_line2:
                    lines.append(f"{order.shipping_line2}")
            if order.shipping_city:
                lines.append(f"{order.shipping_city}, {order.shipping_state} {order.shipping_postal_code}")
            if order.shipping_country:
                lines.append(f"{order.shipping_country}")
            lines.append("")

        lines.append("Mark items as shipped with tracking info in the fulfillment dashboard.")

        subject = f"New order received - #{order.pk}"
        body = "\n".join(lines)

        shipping_lines = ""
        if order.requires_shipping:
            parts = [
                f"{order.shipping_name}",
                f"{order.shipping_line1}",
            ]
            if order.shipping_line2:
                parts.append(order.shipping_line2)
            if order.shipping_city:
                parts.append(f"{order.shipping_city}, {order.shipping_state} {order.shipping_postal_code}")
            if order.shipping_country:
                parts.append(order.shipping_country)
            shipping_lines = "\n".join([p for p in parts if p])

        html_message = render_to_string(
            "emails/seller_new_order.html",
            {
                "subject": subject,
                "logo_url": logo_url,
                "order_id": order.pk,
                "fulfillment_link": fulfillment_link,
                "items": [f"{item.quantity}x {item.product.title} (${item.line_total_cents / 100:.2f})" for item in items],
                "shipping_lines": shipping_lines,
            },
        )

        try:
            send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", None),
                [seller.email],
                html_message=html_message,
            )
        except Exception:
            pass


def _send_buyer_shipped_email(order: "Order", item: "OrderItem") -> None:
    """
    Send notification to buyer when seller ships item with tracking info.
    """
    if item.is_tip:
        return

    recipient_email = ""
    if order.buyer and order.buyer.email:
        recipient_email = order.buyer.email
    elif order.guest_email:
        recipient_email = order.guest_email

    if not recipient_email:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = f"{base}{reverse('orders:detail', kwargs={'order_id': order.pk})}"
    if order.is_guest:
        order_link += f"?t={order.order_token}"

    lines: list[str] = []
    lines.append(f"Your order #{order.pk} has been shipped!")
    lines.append("")
    lines.append(f"Item: {item.product.title}")
    lines.append(f"Quantity: {item.quantity}")
    lines.append("")

    if item.carrier:
        lines.append(f"Carrier: {item.carrier}")
    if item.tracking_number:
        lines.append(f"Tracking number: {item.tracking_number}")
    if item.carrier or item.tracking_number:
        lines.append("")

    lines.append("View your order:")
    lines.append(order_link)
    lines.append("")
    lines.append("Thanks for shopping at Home Craft 3D!")

    subject = f"Your order #{order.pk} has shipped"
    body = "\n".join(lines)

    html_message = render_to_string(
        "emails/buyer_shipped.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": order.pk,
            "order_link": order_link,
            "item_title": item.product.title,
            "quantity": item.quantity,
            "carrier": item.carrier,
            "tracking_number": item.tracking_number,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient_email],
            html_message=html_message,
        )
    except Exception:
        pass


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

    # IMPORTANT: exclude tip lines
    product_ids = list(order.items.filter(is_tip=False).values_list("product_id", flat=True))
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

    marketplace_sales_percent_snapshot = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Marketplace % cut captured at order creation time.",
    )

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
        # IMPORTANT: tips never require shipping
        return self.items.filter(requires_shipping=True, is_tip=False).exists()

    def recompute_totals(self) -> None:
        subtotal = 0
        any_digital = False
        any_physical = False

        for oi in self.items.all():
            subtotal += int(oi.line_total_cents)

            # Ignore tips when determining order kind
            if oi.is_tip:
                continue

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

        if self.status == self.Status.PAID:
            try:
                from payments.services import ensure_sale_balance_entries_for_paid_order

                ensure_sale_balance_entries_for_paid_order(order=self)
            except Exception:
                pass

        if changed:
            msg = note or ""
            if payment_intent_id and payment_intent_id != "FREE":
                msg = msg or f"Marked paid via Stripe PI {payment_intent_id}"
            elif payment_intent_id == "FREE":
                msg = msg or "Marked paid via FREE checkout"
            self._add_event(OrderEvent.Type.PAID, msg)

            _send_paid_order_email(self)
            _send_seller_new_order_email(self)

        return changed

    def mark_canceled(self, *, note: str = "") -> bool:
        if self.status == self.Status.CANCELED:
            return False

        if self.status in {self.Status.PAID, self.Status.REFUNDED}:
            return False

        self.status = self.Status.CANCELED
        self.save(update_fields=["status", "updated_at"])

        msg = (note or "Checkout canceled").strip()
        self._add_event(OrderEvent.Type.CANCELED, msg)

        _send_order_canceled_email(self)
        return True


class OrderItem(models.Model):
    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", "Pending fulfillment"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"

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

    # ✅ NEW: tip lines (do not ship, do not affect kind, no reviews, no downloads)
    is_tip = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this line is a buyer tip (100% to seller; no marketplace fee).",
    )

    buyer_notes = models.TextField(
        blank=True,
        default="",
        help_text="Special instructions or notes from the buyer for this item.",
    )

    marketplace_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="Marketplace fee on this line (percent-based).",
    )
    seller_net_cents = models.PositiveIntegerField(
        default=0,
        help_text="Seller net on this line (gross - marketplace_fee).",
    )

    fulfillment_status = models.CharField(
        max_length=24,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
    )
    carrier = models.CharField(max_length=80, blank=True, default="")
    tracking_number = models.CharField(max_length=255, blank=True, default="")
    shipped_at = models.DateTimeField(null=True, blank=True)
    buyer_notified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "created_at"]),
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["seller", "created_at"]),
            models.Index(fields=["is_tip", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_id}"

    @property
    def line_total_cents(self) -> int:
        return int(self.quantity) * int(self.unit_price_cents)

    def mark_shipped(self, tracking_number: str = "", carrier: str = "") -> bool:
        if self.is_tip:
            return False

        if self.fulfillment_status == self.FulfillmentStatus.SHIPPED:
            return False

        self.fulfillment_status = self.FulfillmentStatus.SHIPPED
        self.tracking_number = (tracking_number or "").strip()
        self.carrier = (carrier or "").strip()
        self.shipped_at = timezone.now()
        self.buyer_notified_at = timezone.now()
        self.save(
            update_fields=[
                "fulfillment_status",
                "tracking_number",
                "carrier",
                "shipped_at",
                "buyer_notified_at",
                "updated_at",
            ]
        )

        _send_buyer_shipped_email(self.order, self)

        return True

    def mark_delivered(self) -> bool:
        if self.is_tip:
            return False

        if self.fulfillment_status == self.FulfillmentStatus.DELIVERED:
            return False

        self.fulfillment_status = self.FulfillmentStatus.DELIVERED
        self.save(update_fields=["fulfillment_status", "updated_at"])
        _send_review_request_email(self.order, self)
        return True


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
