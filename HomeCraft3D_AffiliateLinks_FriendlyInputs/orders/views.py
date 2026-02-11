# orders/views.py

from __future__ import annotations

import logging
import zipfile
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import F, Q, Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from cart.cart import Cart
from core.throttle import throttle
from core.throttle_rules import CHECKOUT_START, DOWNLOAD
from core.recaptcha import require_recaptcha_v3
from payments.utils import seller_is_stripe_ready
from products.models import DigitalAsset, Product, ProductDownloadEvent
from products.permissions import is_owner_user, is_seller_user, seller_required

from .models import Order, OrderItem
from .services import create_order_from_cart, refresh_fulfillment_task_for_seller
from .stripe_service import create_checkout_session_for_order

logger = logging.getLogger(__name__)

CHECKOUT_PLACE_RULE = CHECKOUT_START
CHECKOUT_START_RULE = CHECKOUT_START

# Download endpoints are GETs and can be abused to inflate metrics or waste bandwidth.
DOWNLOAD_ASSET_RULE = DOWNLOAD
DOWNLOAD_BUNDLE_RULE = DOWNLOAD


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
    has_digital_assets = False
    shipping_timeline = None
    if can_download:
        for item in order.items.all():
            if not item.is_digital:
                continue
            try:
                if item.product.digital_assets.exists():
                    has_digital_assets = True
                    break
            except Exception:
                continue

    if order.requires_shipping:
        shipped = False
        delivered = False
        for item in order.items.all():
            if not item.requires_shipping:
                continue
            if item.fulfillment_status == item.FulfillmentStatus.DELIVERED:
                delivered = True
                shipped = True
                break
            if item.fulfillment_status == item.FulfillmentStatus.SHIPPED:
                shipped = True

        shipping_timeline = {
            "paid": order.status == Order.Status.PAID,
            "shipped": shipped,
            "delivered": delivered,
        }

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "order_token": _token_from_request(request),
            "can_download": can_download,
            "has_digital_assets": has_digital_assets,
            "shipping_timeline": shipping_timeline,
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
    order.mark_canceled(note="Checkout canceled by buyer")
    messages.info(request, "Checkout canceled.")
    t = _token_from_request(request)
    if order.is_guest and t:
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={t}")
    return redirect("orders:detail", order_id=order.pk)


@throttle(DOWNLOAD_ASSET_RULE, methods=("GET",))
def download_asset(request, order_id, asset_id):
    logger.info("download_asset start order=%s asset=%s", order_id, asset_id)
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

    # Metrics (best-effort): total download clicks + unique downloaders
    try:
        DigitalAsset.objects.filter(pk=asset.pk).update(download_count=F("download_count") + 1)
        Product.objects.filter(pk=asset.product_id).update(download_count=F("download_count") + 1)

        if not request.session.session_key:
            request.session.create()
        sess = request.session.session_key or ""
        ProductDownloadEvent.objects.create(
            product=asset.product,
            user=request.user if request.user.is_authenticated else None,
            session_key=sess,
        )
    except Exception:
        pass

    file_handle = asset.file.open("rb")
    filename = asset.original_filename or asset.file.name.rsplit("/", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@throttle(DOWNLOAD_BUNDLE_RULE, methods=("GET",))
def download_all_assets(request, order_id):
    logger.info("download_all_assets start order=%s", order_id)
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__product", "items__product__digital_assets"),
        pk=order_id,
    )

    if order.status != Order.Status.PAID:
        raise Http404("Not found")

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    assets = []
    for item in order.items.all():
        if not item.is_digital:
            continue
        try:
            if item.product.kind != Product.Kind.FILE:
                continue
        except Exception:
            continue

        for asset in item.product.digital_assets.all():
            assets.append((item.product, asset))

    if not assets:
        raise Http404("Not found")

    # Metrics (best-effort): count this "Download all" click once per product,
    # and bump per-asset counters for visibility on detail pages.
    try:
        if not request.session.session_key:
            request.session.create()
        sess = request.session.session_key or ""

        product_ids = sorted({p.pk for p, _ in assets})
        if product_ids:
            Product.objects.filter(pk__in=product_ids).update(download_count=F("download_count") + 1)
            ProductDownloadEvent.objects.bulk_create(
                [
                    ProductDownloadEvent(
                        product_id=pid,
                        user=request.user if request.user.is_authenticated else None,
                        session_key=sess,
                    )
                    for pid in product_ids
                ],
                ignore_conflicts=False,
            )

        asset_ids = [a.pk for _, a in assets]
        if asset_ids:
            DigitalAsset.objects.filter(pk__in=asset_ids).update(download_count=F("download_count") + 1)
    except Exception:
        pass

    buffer = SpooledTemporaryFile(max_size=20 * 1024 * 1024)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for product, asset in assets:
            try:
                asset.file.open("rb")
                raw_name = asset.original_filename or asset.file.name.rsplit("/", 1)[-1]
                safe_product = slugify(getattr(product, "title", "product") or "product")
                safe_name = raw_name.replace("/", "-").replace("\\", "-")
                zip_name = f"{safe_product}/{safe_name}"
                zf.writestr(zip_name, asset.file.read())
            except Exception:
                continue
            finally:
                try:
                    asset.file.close()
                except Exception:
                    pass

    buffer.seek(0)
    filename = f"order-{order.id}-downloads.zip"
    return FileResponse(buffer, as_attachment=True, filename=filename)


@login_required
def purchases(request):
    qs = (
        Order.objects.filter(buyer=request.user, status=Order.Status.PAID, paid_at__isnull=False)
        .prefetch_related("items", "items__product", "items__product__digital_assets")
        .order_by("-paid_at", "-created_at")
    )

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page") or 1)

    orders = list(page.object_list)
    for order in orders:
        has_assets = False
        for item in order.items.all():
            if not item.is_digital:
                continue
            try:
                if item.product.digital_assets.exists():
                    has_assets = True
                    break
            except Exception:
                continue
        order.has_digital_assets = has_assets

    return render(request, "orders/purchases.html", {"page_obj": page, "orders": orders})


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
    """Seller fulfillment queue.

    Shows PAID orders and the seller's *physical* line items that still require action.
    Primary view is the pending queue (unfulfilled physical items).
    """
    user = request.user
    if not (is_seller_user(user) or is_owner_user(user)):
        messages.info(request, "You don’t have access to seller orders.")
        return redirect("dashboards:consumer")

    status = (request.GET.get("status") or "pending").strip().lower()
    if status not in {"pending", "shipped", "delivered", "all"}:
        status = "pending"

    qs = (
        OrderItem.objects.filter(order__status=Order.Status.PAID, order__paid_at__isnull=False, requires_shipping=True)
        .select_related("order", "product", "seller")
        .order_by("-order__paid_at", "-created_at")
    )

    if not is_owner_user(user):
        qs = qs.filter(seller=user)

    if status == "pending":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.PENDING)
    elif status == "shipped":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.SHIPPED)
    elif status == "delivered":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.DELIVERED)

    # Counters for tabs (seller-scoped)
    base_counter_qs = OrderItem.objects.filter(
        order__status=Order.Status.PAID,
        order__paid_at__isnull=False,
        requires_shipping=True,
    )
    if not is_owner_user(user):
        base_counter_qs = base_counter_qs.filter(seller=user)

    counts = base_counter_qs.aggregate(
        pending=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.PENDING)),
        shipped=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.SHIPPED)),
        delivered=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.DELIVERED)),
        total=Count("id"),
    )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "orders/seller_orders_list.html",
        {
            "page_obj": page,
            "items": page.object_list,
            "status": status,
            "counts": counts,
        },
    )

@login_required
@require_POST
def mark_item_delivered_buyer(request, order_id, item_id):
    """
    Buyer confirms a shipped physical line item was delivered.
    Only allowed for the authenticated buyer on their own paid order.
    """
    order = get_object_or_404(Order, id=order_id)

    # Only the buyer can confirm delivery
    if getattr(order, "buyer_id", None) != request.user.id:
        raise Http404()

    item = get_object_or_404(OrderItem, id=item_id, order=order)

    # Guardrails
    if item.is_digital or item.is_tip or not item.requires_shipping:
        raise Http404()

    if getattr(order, "status", "") != Order.Status.PAID:
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:detail", order_id=order.id)

    if item.fulfillment_status != OrderItem.FulfillmentStatus.SHIPPED:
        messages.info(request, "This item can only be marked delivered after it’s shipped.")
        return redirect("orders:detail", order_id=order.id)

    item.mark_delivered()
    messages.success(request, "Marked as delivered. Thanks!")

    return redirect("orders:detail", order_id=order.id)


def _ensure_seller_can_access_order(request, order: Order) -> None:
    """
    Seller can access an order if at least one line item belongs to them.
    Owner/admin is allowed too (if you have that concept, the decorator likely handles it).
    """
    qs = OrderItem.objects.filter(order=order, seller=request.user)
    if not qs.exists():
        raise Http404()


def _seller_line_item_or_404(request, order: Order, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order=order)
    if getattr(item, "seller_id", None) != request.user.id:
        raise Http404()
    return item


@login_required
@seller_required
def seller_order_detail(request, order_id):
    """
    Seller view of a single order: shows only this seller's line items.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    seller_items = (
        OrderItem.objects.filter(order=order, seller=request.user)
        .select_related("product")
        .order_by("created_at")
    )

    # Useful rollups for template
    has_physical = any(getattr(i, "requires_shipping", False) for i in seller_items)
    has_digital = any(getattr(i, "is_digital", False) for i in seller_items)

    context = {
        "order": order,
        "items": seller_items,
        "has_physical": has_physical,
        "has_digital": has_digital,
    }
    return render(request, "orders/seller_order_detail.html", context)


@login_required
@seller_required
@require_POST
def mark_item_shipped(request, order_id, item_id):
    """
    Seller marks a physical line item as shipped.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    item = _seller_line_item_or_404(request, order, item_id)

    # Guardrails
    if getattr(item, "is_digital", False) or getattr(item, "is_tip", False) or not getattr(item, "requires_shipping", False):
        raise Http404()

    # Only for paid orders
    if getattr(order, "status", "") != getattr(Order, "Status", Order).PAID:
        # Works whether Order.Status exists or not
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    # Mark shipped
    if hasattr(item, "mark_shipped"):
        item.mark_shipped()
    else:
        # Fallback: set fulfillment_status + timestamp fields if they exist
        if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
            item.fulfillment_status = OrderItem.FulfillmentStatus.SHIPPED
        if hasattr(item, "shipped_at"):
            from django.utils import timezone
            item.shipped_at = timezone.now()
        item.save(update_fields=[f for f in ["fulfillment_status", "shipped_at"] if hasattr(item, f)])

    messages.success(request, "Marked as shipped.")
    return redirect("orders:seller_order_detail", order_id=order.id)


@login_required
@seller_required
@require_POST
def mark_item_delivered(request, order_id, item_id):
    """
    Seller marks a physical line item as delivered (optional workflow).
    Buyer-confirm-delivered also exists separately.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    item = _seller_line_item_or_404(request, order, item_id)

    # Guardrails
    if getattr(item, "is_digital", False) or getattr(item, "is_tip", False) or not getattr(item, "requires_shipping", False):
        raise Http404()

    if getattr(order, "status", "") != getattr(Order, "Status", Order).PAID:
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    # Optional guard: only allow delivered after shipped
    if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
        if item.fulfillment_status != OrderItem.FulfillmentStatus.SHIPPED:
            messages.info(request, "Mark shipped first.")
            return redirect("orders:seller_order_detail", order_id=order.id)

    # Mark delivered
    if hasattr(item, "mark_delivered"):
        item.mark_delivered()
    else:
        if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
            item.fulfillment_status = OrderItem.FulfillmentStatus.DELIVERED
        if hasattr(item, "delivered_at"):
            from django.utils import timezone
            item.delivered_at = timezone.now()
        item.save(update_fields=[f for f in ["fulfillment_status", "delivered_at"] if hasattr(item, f)])

    messages.success(request, "Marked as delivered.")
    return redirect("orders:seller_order_detail", order_id=order.id)

