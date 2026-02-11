# refunds/stripe_service.py

from __future__ import annotations

import stripe
from django.conf import settings

from .models import RefundRequest


def _init_stripe() -> None:
    key = getattr(settings, "STRIPE_SECRET_KEY", None)
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
    stripe.api_key = key


def create_stripe_refund_for_request(*, rr: RefundRequest) -> str:
    """
    Create a Stripe refund for this request.

    Source of truth:
      - refund amount = rr.total_refund_cents_snapshot
      - target payment = rr.order.stripe_payment_intent_id

    Idempotency:
      - idempotency_key=f"refundreq-{rr.pk}"
    """
    _init_stripe()

    order = rr.order
    payment_intent = (getattr(order, "stripe_payment_intent_id", "") or "").strip()

    # FREE checkouts have no Stripe refund
    if payment_intent == "FREE":
        raise ValueError("Order was a free checkout; no Stripe refund is possible.")

    if not payment_intent:
        raise ValueError("Order has no Stripe payment intent id; cannot refund.")

    amount = int(getattr(rr, "total_refund_cents_snapshot", 0) or 0)
    if amount <= 0:
        raise ValueError("Refund amount must be > 0.")

    refund = stripe.Refund.create(
        payment_intent=payment_intent,
        amount=amount,
        metadata={
            "refund_request_id": str(rr.pk),
            "order_id": str(order.pk),
            "order_item_id": str(rr.order_item_id),
            "seller_id": str(rr.seller_id),
        },
        idempotency_key=f"refundreq-{rr.pk}",
    )

    refund_id = str(getattr(refund, "id", "") or "").strip()
    if not refund_id:
        raise ValueError("Stripe did not return a refund id.")
    return refund_id
