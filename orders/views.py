# orders/views.py

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from cart.cart import Cart
from core.throttle import ThrottleRule, throttle
from core.recaptcha import require_recaptcha_v3
from payments.utils import seller_is_stripe_ready
from products.models import DigitalAsset, Product
from products.permissions import is_owner_user, is_seller_user

from .models import Order
from .services import create_order_from_cart
from .stripe_service import create_checkout_session_for_order

logger = logging.getLogger(__name__)

CHECKOUT_PLACE_RULE = ThrottleRule(key_prefix="checkout_place_order", limit=6, window_seconds=60)
CHECKOUT_START_RULE = ThrottleRule(key_prefix="checkout_start", limit=8, window_seconds=60)


def _token_from_request(request) -> str:
    return (request.GET.get("t") or "").strip()


def _normalize_guest_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not email:
        return ""
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def _is_owner_request(request) -> bool:
    try:
        return bool(request.user.is_authenticated and is_owner_user(request.user))
    except Exception:
        return False


def _user_can_access_order(request, order: Order) -> bool:
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return True

    if getattr(order, "buyer_id", None):
        return request.user.is_authenticated and request.user.id == order.buyer_id

    t = _token_from_request(request)
    return bool(t) and str(t) == str(getattr(order, "order_token", ""))


def _order_has_unready_sellers(request, order: Order) -> list[str]:
    """
    IMPORTANT: Owner bypass is based on request.user.
    """
    if _is_owner_request(request):
        return []

    bad: list[str] = []
    for item in order.items.select_related("seller").all():
        seller = getattr(item, "seller", None)
        if seller and not seller_is_stripe_ready(seller):
            bad.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    seen: set[str] = set()
    out: list[str] = []
    for u in bad:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _cart_has_unready_sellers(request, cart: Cart) -> list[str]:
    """
    IMPORTANT: Owner bypass is based on request.user.
    """
    if _is_owner_request(request):
        return []

    bad: list[str] = []
    for line in cart.lines():
        product = getattr(line, "product", None)
        seller = getattr(product, "seller", None)
        if seller and not seller_is_stripe_ready(seller):
            bad.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    seen: set[str] = set()
    out: list[str] = []
    for u in bad:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _cart_inactive_titles(cart: Cart) -> list[str]:
    bad: list[str] = []
    for line in cart.lines():
        p = getattr(line, "product", None)
        if not p:
            continue
        if not getattr(p, "is_active", True):
            bad.append(getattr(p, "title", str(getattr(p, "pk", ""))))
    seen = set()
    out: list[str] = []
    for t in bad:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _order_inactive_titles(order: Order) -> list[str]:
    bad: list[str] = []
    for item in order.items.select_related("product").all():
        p = getattr(item, "product", None)
        if not p:
            bad.append("Unknown item")
            continue
        if not getattr(p, "is_active", True):
            bad.append(getattr(p, "title", str(getattr(p, "pk", ""))))
    seen = set()
    out: list[str] = []
    for t in bad:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _require_legal_acceptance_or_redirect(request, *, guest_email: str = "", next_url: str = ""):
    return None


@require_POST
@throttle(CHECKOUT_PLACE_RULE)
@require_recaptcha_v3("checkout_place_order")
def place_order(request):
    """
    Create an Order from the cart and immediately launch Stripe Checkout.

    Important: "Pending" is a *transient* state while we redirect to Stripe.
    If Checkout cannot be created, we keep the order pending and show an error
    (so we don't lose the record), but we do NOT clear the cart until we have
    a Stripe session URL.
    """
    cart = Cart(request)
    if cart.count_items() == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    inactive_titles = _cart_inactive_titles(cart)
    if inactive_titles:
        messages.error(
            request,
            "Some items in your cart are no longer available: " + ", ".join(inactive_titles),
        )
        return redirect("cart:detail")

    bad_sellers = _cart_has_unready_sellers(request, cart)
    if bad_sellers:
        messages.error(
            request,
            "One or more sellers in your cart haven’t completed payout setup yet: " + ", ".join(bad_sellers),
        )
        return redirect("cart:detail")

    guest_email = ""
    if not request.user.is_authenticated:
        guest_email = _normalize_guest_email(request.POST.get("guest_email") or "")
        if not guest_email:
            messages.error(request, "Please enter a valid email to checkout as a guest.")
            return redirect("cart:detail")

    try:
        order = create_order_from_cart(cart, buyer=request.user, guest_email=guest_email)
    except ValueError as e:
        messages.error(request, str(e) or "Your cart can’t be checked out right now.")
        return redirect("cart:detail")

    # If this is a free order, complete immediately (no Stripe)
    if int(order.total_cents or 0) <= 0:
        order.mark_paid(payment_intent_id="FREE")
        cart.clear()
        messages.success(request, "Your order is complete.")
        if order.is_guest:
            return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}")
        return redirect("orders:detail", order_id=order.pk)

    # Create Stripe Checkout session immediately
    try:
        session = create_checkout_session_for_order(request=request, order=order)
    except Exception:
        logger.exception("Failed to create Stripe Checkout session for order=%s", order.pk)
        messages.error(
            request,
            "We couldn’t start Stripe Checkout. Please try again in a moment. "
            "If this keeps happening, contact support."
        )
        # Keep cart intact since payment didn't start; allow retry from order detail.
        if order.is_guest:
            return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}")
        return redirect("orders:detail", order_id=order.pk)

    # Only clear cart after Stripe session exists
    cart.clear()
    messages.info(request, "Redirecting to secure checkout…")
    return redirect(session.url)


def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items",
            "items__seller",
            "items__refund_request",
            "items__product",
            "items__product__digital_assets",
        ),
        pk=order_id,
    )

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    can_download = bool(order.status == Order.Status.PAID and _user_can_access_order(request, order))

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "order_token": _token_from_request(request),
            "can_download": can_download,
            "stripe_publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
        },
    )


@require_POST
@throttle(CHECKOUT_START_RULE)
@require_recaptcha_v3("checkout_start")
def checkout_start(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__seller", "items__product"),
        pk=order_id,
    )

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    guest_email = getattr(order, "guest_email", "") or ""
    legal_redirect = _require_legal_acceptance_or_redirect(
        request,
        guest_email=guest_email,
        next_url=reverse("orders:detail", kwargs={"order_id": order.pk})
        + (f"?t={order.order_token}" if order.is_guest else ""),
    )
    if legal_redirect is not None:
        return legal_redirect

    if order.status != Order.Status.PENDING:
        messages.info(request, "This order is not payable.")
        return redirect("orders:detail", order_id=order.pk)

    if order.items.count() == 0:
        messages.error(request, "Order has no items.")
        return redirect("orders:detail", order_id=order.pk)

    inactive_titles = _order_inactive_titles(order)
    if inactive_titles and not _is_owner_request(request):
        messages.error(
            request,
            "One or more items in this order are no longer available: " + ", ".join(inactive_titles),
        )
        return redirect("orders:detail", order_id=order.pk)

    bad_sellers = _order_has_unready_sellers(request, order)
    if bad_sellers:
        messages.error(
            request,
            "One or more sellers in this order haven’t completed payout setup yet: " + ", ".join(bad_sellers),
        )
        return redirect("orders:detail", order_id=order.pk)

    if int(order.total_cents or 0) <= 0:
        order.mark_paid(payment_intent_id="FREE")
        messages.success(request, "Your order is complete.")
        if order.is_guest:
            return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}")
        return redirect("orders:detail", order_id=order.pk)

    session = create_checkout_session_for_order(request=request, order=order)
    return redirect(session.url)


def checkout_success(request):
    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        messages.info(request, "Checkout completed. If your order doesn't update immediately, refresh in a moment.")
        return redirect("home")

    order = Order.objects.filter(stripe_session_id=session_id).first()

    order_detail_url = ""
    if order:
        if order.is_guest:
            order_detail_url = f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}"
        else:
            order_detail_url = reverse("orders:detail", kwargs={"order_id": order.pk})

    return render(request, "orders/checkout_success.html", {"order": order, "order_detail_url": order_detail_url})


def checkout_cancel(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    messages.info(request, "Checkout canceled.")
    t = _token_from_request(request)
    if order.is_guest and t:
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={t}")
    return redirect("orders:detail", order_id=order.pk)


def download_asset(request, order_id, asset_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__product"),
        pk=order_id,
    )

    if order.status != Order.Status.PAID:
        raise Http404("Not found")

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    asset = get_object_or_404(DigitalAsset.objects.select_related("product"), pk=asset_id)

    order_product_ids = set(order.items.values_list("product_id", flat=True))
    if asset.product_id not in order_product_ids:
        raise Http404("Not found")

    if asset.product.kind != Product.Kind.FILE:
        raise Http404("Not found")

    file_handle = asset.file.open("rb")
    filename = asset.original_filename or asset.file.name.rsplit("/", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@login_required
@login_required
def purchases(request):
    qs = (
        Order.objects.filter(buyer=request.user, status=Order.Status.PAID, paid_at__isnull=False)
        .prefetch_related("items", "items__product", "items__product__digital_assets")
        .order_by("-paid_at", "-created_at")
    )

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(request, "orders/purchases.html", {"page_obj": page, "orders": page.object_list})


@login_required
def my_orders(request):
    qs = (
        Order.objects.filter(buyer=request.user)
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "orders/my_orders.html", {"page_obj": page, "orders": page.object_list})


@login_required
def seller_orders_list(request):
    user = request.user
    if not (is_seller_user(user) or is_owner_user(user)):
        messages.info(request, "You don’t have access to seller orders.")
        return redirect("dashboards:consumer")

    qs = (
        Order.objects.filter(status=Order.Status.PAID, paid_at__isnull=False)
        .prefetch_related("items", "items__product", "items__seller")
        .order_by("-paid_at", "-created_at")
    )

    if not is_owner_user(user):
        qs = qs.filter(items__seller=user).distinct()

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "orders/seller_orders_list.html", {"page_obj": page, "orders": page.object_list})


@login_required
def seller_order_detail(request, order_id):
    user = request.user
    if not (is_seller_user(user) or is_owner_user(user)):
        messages.info(request, "You don’t have access to seller orders.")
        return redirect("dashboards:consumer")

    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__product", "items__seller"),
        pk=order_id,
    )

    if not is_owner_user(user):
        if not order.items.filter(seller=user).exists():
            return redirect("orders:seller_orders_list")

    seller_items = order.items.select_related("product", "seller").all()
    if not is_owner_user(user):
        seller_items = seller_items.filter(seller=user)

    return render(request, "orders/seller_order_detail.html", {"order": order, "seller_items": seller_items})
