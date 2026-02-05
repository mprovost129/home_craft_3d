from __future__ import annotations

import logging
from typing import List, Tuple

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.throttle import ThrottleRule, throttle
from payments.utils import seller_is_stripe_ready
from products.models import Product, ProductEngagementEvent
from products.permissions import is_owner_user

from .cart import Cart

logger = logging.getLogger(__name__)


# ============================================================
# Throttle rules
# ============================================================
CART_ADD_RULE = ThrottleRule(key_prefix="cart_add", limit=12, window_seconds=60)
CART_UPDATE_RULE = ThrottleRule(key_prefix="cart_update", limit=18, window_seconds=60)
CART_REMOVE_RULE = ThrottleRule(key_prefix="cart_remove", limit=18, window_seconds=60)
CART_CLEAR_RULE = ThrottleRule(key_prefix="cart_clear", limit=6, window_seconds=60)


# ============================================================
# Helpers
# ============================================================
def _is_owner_request(request) -> bool:
    try:
        return bool(request.user.is_authenticated and is_owner_user(request.user))
    except Exception:
        return False


def _clamp_quantity(qty: int) -> int:
    # Keep it simple for v1. You can add per-product max later.
    if qty < 1:
        return 1
    if qty > 20:
        return 20
    return qty


def _seller_block_reason(*, request, product: Product) -> str | None:
    """
    Return a human-readable reason if a product cannot be purchased.

    IMPORTANT:
    - Owner bypass is based on request.user (not the product's seller).
    - Seller readiness is enforced server-side for cart add/update and order placement.
    """
    if _is_owner_request(request):
        return None

    if not getattr(product, "is_active", True):
        return "This item is not available right now."

    seller = getattr(product, "seller", None)
    if seller and not seller_is_stripe_ready(seller):
        return "Seller hasn’t completed payout setup yet."

    return None


def _enforce_file_quantity(product: Product, quantity: int) -> int:
    """
    Digital FILE items must always be qty=1.
    """
    try:
        if getattr(product, "kind", None) == Product.Kind.FILE:
            return 1
    except Exception:
        # If enum isn't available for some reason, don't blow up.
        pass
    return quantity


def _log_add_to_cart_throttled(request, *, product: Product) -> None:
    """
    Log ADD_TO_CART with a simple session throttle to avoid spam.
    (One per session per product.)
    """
    try:
        key = f"hc3_event_add_to_cart_{product.id}"
        if request.session.get(key):
            return
        ProductEngagementEvent.objects.create(
            product=product,
            event_type=ProductEngagementEvent.EventType.ADD_TO_CART,
        )
        request.session[key] = True
        request.session.modified = True
    except Exception:
        return


def _prune_blocked_items(request, cart: Cart) -> Tuple[List[str], List[str]]:
    """
    Remove items that are no longer purchasable (seller not ready, inactive, etc.)
    Returns (removed_product_titles, unready_seller_usernames).
    """
    removed_titles: List[str] = []
    unready: List[str] = []

    for line in cart.lines():
        product = line.product

        # Inactive → remove
        if not getattr(product, "is_active", True):
            cart.remove(product)
            removed_titles.append(getattr(product, "title", str(product.pk)))
            continue

        reason = _seller_block_reason(request=request, product=product)
        if reason:
            cart.remove(product)
            removed_titles.append(getattr(product, "title", str(product.pk)))
            try:
                unready.append(getattr(product.seller, "username", "Seller"))
            except Exception:
                unready.append("Seller")

    # de-dupe seller list while preserving order
    seen = set()
    unready_sellers: List[str] = []
    for u in unready:
        if u in seen:
            continue
        seen.add(u)
        unready_sellers.append(u)

    return removed_titles, unready_sellers


# ============================================================
# Views
# ============================================================
def cart_detail(request):
    cart = Cart(request)

    removed_titles, unready_sellers = _prune_blocked_items(request, cart)
    if removed_titles:
        messages.warning(
            request,
            "Some items were removed from your cart because they can’t be checked out right now: "
            + ", ".join(removed_titles),
        )

    cart_lines = cart.lines()
    subtotal = cart.subtotal()
    can_checkout = bool(cart_lines) and not bool(unready_sellers)

    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "cart_lines": cart_lines,
            "subtotal": subtotal,
            "unready_sellers": unready_sellers,
            "can_checkout": can_checkout,
            # Template helper (avoid hardcoding "FILE" in templates)
            "KIND_FILE": getattr(Product.Kind, "FILE", "file"),
        },
    )


@require_POST
@throttle(CART_ADD_RULE)
def cart_add(request):
    cart = Cart(request)

    product_id = (request.POST.get("product_id") or "").strip()
    qty_raw = (request.POST.get("quantity") or "1").strip()
    buyer_notes = (request.POST.get("buyer_notes") or "").strip()[:1000]  # Limit to 1000 chars

    try:
        quantity = int(qty_raw)
    except Exception:
        quantity = 1

    product = get_object_or_404(
        Product.objects.select_related("seller", "category").prefetch_related("images"),
        pk=product_id,
        is_active=True,
    )

    reason = _seller_block_reason(request=request, product=product)
    if reason:
        messages.error(request, reason)
        return redirect(product.get_absolute_url())

    quantity = _clamp_quantity(quantity)
    forced = _enforce_file_quantity(product, quantity)
    if forced != quantity:
        quantity = forced
        messages.info(request, "Digital items are limited to 1 per cart.")

    cart.add(product, quantity=quantity, buyer_notes=buyer_notes)
    _log_add_to_cart_throttled(request, product=product)

    messages.success(request, "Added to cart.")

    next_url = (request.POST.get("next") or "").strip()
    if next_url:
        return redirect(next_url)

    referer = (request.META.get("HTTP_REFERER") or "").strip()
    if referer:
        return redirect(referer)

    return redirect(product.get_absolute_url())


@require_POST
@throttle(CART_UPDATE_RULE)
def cart_update(request):
    cart = Cart(request)

    product_id = (request.POST.get("product_id") or "").strip()
    qty_raw = (request.POST.get("quantity") or "1").strip()

    try:
        quantity = int(qty_raw)
    except Exception:
        quantity = 1

    product = get_object_or_404(Product.objects.select_related("seller"), pk=product_id)

    if not product.is_active:
        cart.remove(product)
        messages.info(request, "Item removed (no longer available).")
        return redirect("cart:detail")

    reason = _seller_block_reason(request=request, product=product)
    if reason:
        cart.remove(product)
        messages.error(request, f"Removed from cart: {reason}")
        return redirect("cart:detail")

    quantity = _clamp_quantity(quantity)
    forced = _enforce_file_quantity(product, quantity)
    if forced != quantity:
        quantity = forced
        messages.info(request, "Digital items are limited to 1 per cart.")

    cart.set_quantity(product, quantity)
    messages.success(request, "Cart updated.")
    return redirect("cart:detail")


@require_POST
@throttle(CART_REMOVE_RULE)
def cart_remove(request, product_id: int):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    cart.remove(product)
    messages.info(request, "Item removed.")
    return redirect("cart:detail")


@require_POST
@throttle(CART_CLEAR_RULE)
def cart_clear(request):
    cart = Cart(request)
    cart.clear()
    messages.info(request, "Cart cleared.")
    return redirect("cart:detail")
