from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from cart.cart import Cart
from products.models import Product
from payments.utils import seller_is_stripe_ready

from .models import Order, OrderItem


@transaction.atomic
def create_order_from_cart(cart: Cart, *, buyer, guest_email: str = "") -> Order:
    """
    Create an Order and OrderItems from the session cart.

    HARD RULE:
    - You cannot create an order for products whose seller is not Stripe-ready.
    """
    items = list(cart.items())
    if not items:
        raise ValueError("Cart empty")

    # Validate all items BEFORE creating the order
    bad_sellers = []
    for entry in items:
        product: Product = entry["product"]
        if not seller_is_stripe_ready(product.seller):
            bad_sellers.append(product.seller.username)

    if bad_sellers:
        # Deduplicate while preserving order
        seen = set()
        bad_sellers_unique = [u for u in bad_sellers if not (u in seen or seen.add(u))]
        raise ValueError(
            "Seller not ready for checkout: " + ", ".join(bad_sellers_unique)
        )

    # Create order
    order = Order.objects.create(
        buyer=buyer if getattr(buyer, "is_authenticated", False) else None,
        guest_email=guest_email or "",
        status=Order.Status.PENDING,
        currency="USD",
        subtotal=Decimal("0.00"),
    )

    subtotal = Decimal("0.00")

    for entry in items:
        product: Product = entry["product"]
        qty = int(entry["quantity"])
        unit_price = Decimal(entry["unit_price"])

        line_total = (unit_price * qty).quantize(Decimal("0.01"))
        subtotal += line_total

        OrderItem.objects.create(
            order=order,
            product=product,
            seller=product.seller,
            kind=product.kind,
            title=product.title,
            unit_price=unit_price,
            quantity=qty,
            line_total=line_total,
        )

    order.subtotal = subtotal.quantize(Decimal("0.01"))
    order.save(update_fields=["subtotal", "updated_at"])

    # Ensure guest magic link token exists if guest checkout
    if order.buyer_id is None:
        order.ensure_access_token()

    # Clear cart only after success
    cart.clear()

    return order
