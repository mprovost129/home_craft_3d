from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.cart import Cart
from products.models import Product, DigitalAsset
from .models import Order
from .services import create_order_from_cart
from .stripe_service import create_checkout_session_for_order, verify_and_parse_webhook


def _token_from_request(request) -> str:
    return (request.GET.get("t") or "").strip()


def _user_can_access_order(request, order: Order) -> bool:
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return True

    if order.buyer_id:
        return request.user.is_authenticated and request.user.id == order.buyer_id

    t = _token_from_request(request)
    return bool(t) and t == order.access_token


@require_POST
def place_order(request):
    cart = Cart(request)
    if cart.count_items() == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    guest_email = ""
    if not request.user.is_authenticated:
        guest_email = (request.POST.get("guest_email") or "").strip()
        if not guest_email:
            messages.error(request, "Please enter your email to checkout as a guest.")
            return redirect("cart:detail")

    try:
        order = create_order_from_cart(cart, buyer=request.user, guest_email=guest_email)
    except ValueError:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    messages.success(request, f"Order #{order.pk} created (pending payment).")
    if order.is_guest:
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.access_token}")
    return redirect("orders:detail", order_id=order.pk)


def order_detail(request, order_id: int):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items",
            "items__product",
            "items__product__digital_assets",
            # ✅ Reviews: reverse OneToOne from OrderItem -> Review (related_name="review")
            "items__review",
        ),
        pk=order_id,
    )

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "order_token": _token_from_request(request),
            "stripe_publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
        },
    )


@require_POST
def checkout_start(request, order_id: int):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=order_id)

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    if order.status != Order.Status.PENDING:
        messages.info(request, "This order is not payable.")
        return redirect("orders:detail", order_id=order.pk)

    if order.items.count() == 0:
        messages.error(request, "Order has no items.")
        return redirect("orders:detail", order_id=order.pk)

    session = create_checkout_session_for_order(request=request, order=order)

    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id", "updated_at"])

    return redirect(session.url)


def checkout_success(request):
    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        messages.info(request, "Checkout completed. If your order doesn't update immediately, refresh in a moment.")
        return redirect("home")

    order = Order.objects.filter(stripe_session_id=session_id).first()
    return render(request, "orders/checkout_success.html", {"order": order})


def checkout_cancel(request, order_id: int):
    order = get_object_or_404(Order, pk=order_id)
    messages.info(request, "Checkout canceled.")
    t = _token_from_request(request)
    if order.is_guest and t:
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={t}")
    return redirect("orders:detail", order_id=order.pk)


def download_asset(request, order_id: int, asset_id: int):
    order = get_object_or_404(Order.objects.prefetch_related("items", "items__product"), pk=order_id)

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


def _email_guest_magic_link(order: Order, request_base_url: str) -> None:
    if not order.guest_email:
        return
    if not order.access_token:
        order.ensure_access_token()

    link = f"{request_base_url}{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.access_token}"

    subject = f"Your Home Craft 3D order #{order.pk}"
    body = (
        "Thanks for your purchase!\n\n"
        "Access your order and downloads here:\n"
        f"{link}\n\n"
        "If you didn’t make this purchase, ignore this email."
    )

    try:
        send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [order.guest_email])
    except Exception:
        return


def _extract_shipping_from_session_obj(session_obj: dict) -> dict:
    """
    Stripe Checkout Session may include:
      - shipping_details (preferred)
      - customer_details (fallback)
    """
    shipping_details = session_obj.get("shipping_details") or {}
    customer_details = session_obj.get("customer_details") or {}

    name = shipping_details.get("name") or customer_details.get("name") or ""
    phone = customer_details.get("phone") or ""
    addr = shipping_details.get("address") or customer_details.get("address") or {}

    return {
        "name": name,
        "phone": phone,
        "line1": addr.get("line1") or "",
        "line2": addr.get("line2") or "",
        "city": addr.get("city") or "",
        "state": addr.get("state") or "",
        "postal_code": addr.get("postal_code") or "",
        "country": addr.get("country") or "",
    }


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return HttpResponseBadRequest("Missing signature")

    try:
        event = verify_and_parse_webhook(payload, sig_header)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        order_id = metadata.get("order_id") or data_object.get("client_reference_id")

        session_id = data_object.get("id", "")
        payment_intent_id = data_object.get("payment_intent", "") or ""

        if order_id:
            try:
                order = Order.objects.select_for_update().get(pk=int(order_id))

                if session_id and not order.stripe_session_id:
                    order.stripe_session_id = session_id
                    order.save(update_fields=["stripe_session_id", "updated_at"])

                order.mark_paid(payment_intent_id=payment_intent_id)

                # Save shipping details if present
                ship = _extract_shipping_from_session_obj(data_object)
                if any([ship["line1"], ship["city"], ship["postal_code"], ship["country"]]):
                    order.set_shipping_from_stripe(**ship)

                # Email guest magic link (best-effort)
                base_url = getattr(settings, "SITE_BASE_URL", "").strip()
                if base_url:
                    _email_guest_magic_link(order, base_url)

            except Order.DoesNotExist:
                pass

    return HttpResponse(status=200)
