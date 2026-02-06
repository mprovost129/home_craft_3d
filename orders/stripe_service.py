# orders/stripe_service.py

from __future__ import annotations

import hashlib
from typing import Any

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import F, IntegerField, Sum
from django.db.models.expressions import ExpressionWrapper
from django.urls import reverse

from core.config import get_allowed_shipping_countries
from payments.models import SellerStripeAccount, SellerBalanceEntry
from payments.services import get_seller_balance_cents
from payments.utils import seller_is_stripe_ready
from products.permissions import is_owner_user

from .models import Order, OrderEvent, _send_payout_email


def _stripe_init() -> None:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _assert_order_sellers_stripe_ready(*, request, order: Order) -> None:
    """
    Defense-in-depth: re-check readiness at checkout start.
    IMPORTANT: use OrderItem.seller snapshot (not product__seller).
    """
    if request.user.is_authenticated and is_owner_user(request.user):
        return

    bad: list[str] = []
    for it in order.items.select_related("seller").all():
        seller = it.seller
        if not seller or not seller_is_stripe_ready(seller):
            bad.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    if bad:
        seen: set[str] = set()
        bad_unique = [u for u in bad if not (u in seen or seen.add(u))]
        raise ValueError("Seller not ready for checkout: " + ", ".join(bad_unique))


def _order_idem_key(order: Order) -> str:
    base = f"{order.pk}:{order.total_cents}:{order.currency}:{order.kind}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    return f"checkout_session:{order.pk}:{digest}:v1"


def create_checkout_session_for_order(*, request, order: Order) -> stripe.checkout.Session:
    _stripe_init()
    _assert_order_sellers_stripe_ready(request=request, order=order)

    line_items: list[dict[str, Any]] = []
    for item in order.items.select_related("product").all():
        product = item.product
        name = getattr(product, "title", None) or getattr(product, "name", None) or f"Product {item.product_id}"

        line_items.append(
            {
                "price_data": {
                    "currency": order.currency.lower(),
                    "product_data": {"name": str(name)},
                    "unit_amount": int(item.unit_price_cents),
                },
                "quantity": int(item.quantity),
            }
        )

    success_url = request.build_absolute_uri(
        reverse("orders:checkout_success") + "?session_id={CHECKOUT_SESSION_ID}"
    )

    cancel_path = reverse("orders:checkout_cancel", kwargs={"order_id": order.pk})
    if order.is_guest:
        cancel_path = f"{cancel_path}?t={order.order_token}"
    cancel_url = request.build_absolute_uri(cancel_path)

    kwargs: dict[str, Any] = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(order.pk),
        "metadata": {
            "order_id": str(order.pk),
            "order_token": str(order.order_token),
            "kind": str(order.kind),
        },
        "payment_intent_data": {
            "metadata": {
                "order_id": str(order.pk),
                "order_token": str(order.order_token),
            }
        },
        "billing_address_collection": "required",
    }

    if order.is_guest and order.guest_email:
        kwargs["customer_email"] = order.guest_email

    if order.requires_shipping:
        kwargs["shipping_address_collection"] = {"allowed_countries": get_allowed_shipping_countries()}
        kwargs["phone_number_collection"] = {"enabled": True}

    session = stripe.checkout.Session.create(
        **kwargs,
        idempotency_key=_order_idem_key(order),
    )

    if not order.stripe_session_id:
        order.stripe_session_id = session.id
        order.save(update_fields=["stripe_session_id", "updated_at"])

    OrderEvent.objects.create(
        order=order,
        type=OrderEvent.Type.STRIPE_SESSION_CREATED,
        message=f"session={session.id}",
    )

    return session


def verify_and_parse_webhook(payload: bytes, sig_header: str):
    _stripe_init()
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=settings.STRIPE_WEBHOOK_SECRET,
    )


def _transfers_already_recorded(order: Order) -> bool:
    return order.events.filter(type=OrderEvent.Type.TRANSFER_CREATED).exists()


@transaction.atomic
def create_transfers_for_paid_order(*, order: Order, payment_intent_id: str) -> None:
    """
    Create Stripe transfers for a PAID order.

    Ledger-aware:
      - Applies seller balance
      - Never overpays
      - Carries negative balances forward
    """
    payment_intent_id = (payment_intent_id or "").strip()
    if not payment_intent_id or payment_intent_id == "FREE":
        return

    if _transfers_already_recorded(order):
        return

    _stripe_init()

    line_total_expr = ExpressionWrapper(
        F("quantity") * F("unit_price_cents"),
        output_field=IntegerField(),
    )

    seller_rows = (
        order.items.select_related("seller")
        .values("seller_id")
        .annotate(
            gross_cents=Sum(line_total_expr),
            net_cents=Sum("seller_net_cents"),
        )
    )

    charge_id = ""
    try:
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        charge_id = str(getattr(pi, "latest_charge", "") or "")
    except Exception:
        charge_id = ""

    for row in seller_rows:
        seller_id = row.get("seller_id")
        gross_cents = int(row.get("gross_cents") or 0)
        net_cents = int(row.get("net_cents") or 0)

        if gross_cents <= 0 or net_cents <= 0 or not seller_id:
            continue

        acct = SellerStripeAccount.objects.filter(user_id=seller_id).first()
        if not acct or not acct.is_ready:
            OrderEvent.objects.create(
                order=order,
                type=OrderEvent.Type.WARNING,
                message=f"transfer skipped seller={seller_id} (not ready)",
            )
            continue

        balance_cents = int(get_seller_balance_cents(seller=acct.user) or 0)
        payout_cents = max(0, net_cents + balance_cents)

        if payout_cents <= 0:
            OrderEvent.objects.create(
                order=order,
                type=OrderEvent.Type.WARNING,
                message=f"transfer skipped seller={seller_id} (balance={balance_cents})",
            )
            continue

        kwargs: dict[str, Any] = {
            "amount": int(payout_cents),
            "currency": order.currency.lower(),
            "destination": acct.stripe_account_id,
            "transfer_group": str(order.pk),
            "metadata": {
                "order_id": str(order.pk),
                "seller_id": str(seller_id),
                "payment_intent_id": str(payment_intent_id),
                "gross_cents": str(gross_cents),
                "net_cents": str(net_cents),
                "seller_balance_before": str(balance_cents),
            },
        }

        if charge_id:
            kwargs["source_transaction"] = charge_id

        transfer = stripe.Transfer.create(
            **kwargs,
            idempotency_key=f"transfer:{order.pk}:{seller_id}:v4",
        )

        SellerBalanceEntry.objects.create(
            seller=acct.user,
            amount_cents=-int(payout_cents),
            reason=SellerBalanceEntry.Reason.PAYOUT,
            order=order,
            note=f"Stripe transfer {transfer.id}",
        )

        _send_payout_email(
            order=order,
            seller=acct.user,
            payout_cents=int(payout_cents),
            balance_before_cents=int(balance_cents),
            transfer_id=str(getattr(transfer, "id", "") or ""),
        )

        OrderEvent.objects.create(
            order=order,
            type=OrderEvent.Type.TRANSFER_CREATED,
            message=(
                f"transfer={transfer.id} seller={seller_id} "
                f"gross={gross_cents} net={net_cents} "
                f"balance_before={balance_cents} payout={payout_cents}"
            ),
        )
