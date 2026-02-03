# orders/services.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from django.db import transaction

from core.config import get_site_config
from payments.utils import money_to_cents
from products.models import Product

from .models import LineItem, Order, OrderEvent


@dataclass(frozen=True)
class ShippingSnapshot:
    name: str = ""
    phone: str = ""
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _iter_cart_items(cart_or_items) -> Iterable:
    if hasattr(cart_or_items, "lines") and callable(getattr(cart_or_items, "lines")):
        return cart_or_items.lines()
    return cart_or_items


def _cents_round(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _pct_to_rate(pct: Decimal) -> Decimal:
    try:
        return Decimal(pct) / Decimal("100")
    except Exception:
        return Decimal("0")


def _compute_marketplace_fee_cents(*, gross_cents: int, sales_rate: Decimal) -> int:
    gross = Decimal(int(gross_cents))
    fee = gross * (sales_rate or Decimal("0"))
    return max(0, _cents_round(fee))


@transaction.atomic
def create_order_from_cart(
    cart_or_items=None,
    *,
    cart_items=None,
    buyer,
    guest_email: str,
    currency: str = "usd",
    shipping: Optional[ShippingSnapshot] = None,
) -> Order:
    """
    Create an Order + OrderItems from a session Cart (or an iterable of cart lines).

    Rules:
      - Snapshot SiteConfig percent onto Order at creation time
      - Snapshot seller onto each OrderItem at purchase time
      - Compute per-line ledger fields:
          marketplace_fee_cents, seller_net_cents

    Platform fee:
      - NOT USED. Forced to 0 (legacy field remains).
    """
    items_iterable = cart_items if cart_items is not None else cart_or_items

    buyer_obj = buyer if getattr(buyer, "is_authenticated", False) else None
    guest_email = normalize_email(guest_email)

    if buyer_obj is None and not guest_email:
        raise ValueError("Guest checkout requires a valid email address.")

    cfg = get_site_config()
    sales_pct = Decimal(getattr(cfg, "marketplace_sales_percent", Decimal("0.00")) or Decimal("0.00"))

    order = Order.objects.create(
        buyer=buyer_obj,
        guest_email=guest_email if buyer_obj is None else "",
        currency=(currency or "usd").lower(),
        status=Order.Status.PENDING,
        marketplace_sales_percent_snapshot=sales_pct,
        platform_fee_cents_snapshot=0,  # legacy: no platform fee
    )

    if shipping:
        order.shipping_name = shipping.name
        order.shipping_phone = shipping.phone
        order.shipping_line1 = shipping.line1
        order.shipping_line2 = shipping.line2
        order.shipping_city = shipping.city
        order.shipping_state = shipping.state
        order.shipping_postal_code = shipping.postal_code
        order.shipping_country = shipping.country

    items = _iter_cart_items(items_iterable)
    sales_rate = _pct_to_rate(order.marketplace_sales_percent_snapshot)

    line_items: list[LineItem] = []
    for item in items:
        product = getattr(item, "product", None)
        if product is None:
            raise ValueError("Cart line missing product.")

        seller = getattr(product, "seller", None)
        if seller is None:
            raise ValueError(f"Product {getattr(product, 'pk', '')} has no seller.")

        qty = int(getattr(item, "quantity", 1) or 1)

        if hasattr(item, "unit_price_cents"):
            unit_price_cents = int(getattr(item, "unit_price_cents") or 0)
        else:
            unit_price = getattr(item, "unit_price", None)
            unit_price_cents = money_to_cents(unit_price)

        is_digital = bool(getattr(product, "kind", "") == Product.Kind.FILE)
        requires_shipping = bool(getattr(product, "kind", "") == Product.Kind.MODEL)

        if is_digital:
            qty = 1

        gross_cents = max(0, int(qty) * int(unit_price_cents))
        marketplace_fee_cents = _compute_marketplace_fee_cents(gross_cents=gross_cents, sales_rate=sales_rate)
        seller_net_cents = max(0, gross_cents - marketplace_fee_cents)

        line_items.append(
            LineItem(
                order=order,
                product=product,
                seller=seller,
                quantity=qty,
                unit_price_cents=unit_price_cents,
                is_digital=is_digital,
                requires_shipping=requires_shipping,
                marketplace_fee_cents=marketplace_fee_cents,
                seller_net_cents=seller_net_cents,
            )
        )

    LineItem.objects.bulk_create(line_items)

    order.recompute_totals()
    order.save(
        update_fields=[
            "subtotal_cents",
            "tax_cents",
            "shipping_cents",
            "total_cents",
            "kind",
            "shipping_name",
            "shipping_phone",
            "shipping_line1",
            "shipping_line2",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "status",
            "updated_at",
        ]
    )

    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.CREATED)
    except Exception:
        pass

    return order


@transaction.atomic
def mark_order_paid(*, order: Order, stripe_payment_intent_id: str = "") -> Order:
    """Legacy helper (prefer Order.mark_paid)."""
    order.mark_paid(payment_intent_id=stripe_payment_intent_id)
    return order
