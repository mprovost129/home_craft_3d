from __future__ import annotations

from decimal import Decimal

import stripe
from django.conf import settings
from django.urls import reverse

from .models import Order


def _money_to_cents(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1")))


def order_requires_shipping(order: Order) -> bool:
    # Any physical MODEL item triggers shipping address collection
    return order.items.filter(kind="MODEL").exists()


def create_checkout_session_for_order(*, request, order: Order) -> stripe.checkout.Session:
    stripe.api_key = settings.STRIPE_SECRET_KEY

    line_items = []
    for item in order.items.all():
        unit_amount = _money_to_cents(item.unit_price)
        line_items.append(
            {
                "price_data": {
                    "currency": order.currency.lower(),
                    "product_data": {"name": item.title},
                    "unit_amount": unit_amount,
                },
                "quantity": int(item.quantity),
            }
        )

    success_url = request.build_absolute_uri(
        reverse("orders:checkout_success") + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(reverse("orders:checkout_cancel", kwargs={"order_id": order.pk}))

    kwargs = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(order.pk),
        "metadata": {"order_id": str(order.pk)},
        "billing_address_collection": "required",
        "payment_intent_data": {"metadata": {"order_id": str(order.pk)}},
    }

    if order_requires_shipping(order):
        # Capture shipping address & phone for physical goods
        kwargs["shipping_address_collection"] = {"allowed_countries": ["US"]}
        kwargs["phone_number_collection"] = {"enabled": True}

    session = stripe.checkout.Session.create(**kwargs)
    return session


def verify_and_parse_webhook(payload: bytes, sig_header: str):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=settings.STRIPE_WEBHOOK_SECRET,
    )
