# orders/webhooks.py

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from payments.models import SellerBalanceEntry
from payments.services import ensure_sale_balance_entries_for_paid_order

from .models import Order, OrderEvent, StripeWebhookEvent, StripeWebhookDelivery, _send_order_failed_email
from .stripe_service import create_transfers_for_paid_order, verify_and_parse_webhook

logger = logging.getLogger(__name__)


def _extract_shipping_from_session_obj(session_obj: dict) -> dict:
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


def _get_order_id_from_event(event: dict) -> str:
    obj = (event.get("data") or {}).get("object") or {}
    metadata = obj.get("metadata") or {}

    order_id = (metadata.get("order_id") or "").strip()
    if order_id:
        return order_id

    order_id = (obj.get("client_reference_id") or "").strip()
    if order_id:
        return order_id

    return ""


def _record_event_once(*, stripe_event_id: str, event_type: str) -> bool:
    _, created = StripeWebhookEvent.objects.get_or_create(
        stripe_event_id=stripe_event_id,
        defaults={"event_type": event_type or ""},
    )
    return created


def _transfers_already_created(order: Order) -> bool:
    return order.events.filter(type=OrderEvent.Type.TRANSFER_CREATED).exists()


@dataclass(frozen=True)
class _RefundAllocation:
    order_item_id: str
    seller_id: str
    debit_cents: int


def _allocate_refund_across_items(*, order: Order, refund_total_cents: int) -> list[_RefundAllocation]:
    """
    Allocate refund across eligible items proportional to seller_net_cents.

    Integer-safe:
      - share_i = floor(refund_total * net_i / total_net) for all but last
      - last gets remainder
      - each seller debit is capped at that line's net
    """
    refund_total_cents = max(0, int(refund_total_cents or 0))
    items_all = list(order.items.all())
    if refund_total_cents <= 0 or not items_all:
        return []

    eligible = [it for it in items_all if int(getattr(it, "seller_net_cents", 0) or 0) > 0]
    if not eligible:
        return []

    nets = [int(it.seller_net_cents or 0) for it in eligible]
    total_net = sum(nets)
    if total_net <= 0:
        return []

    allocations: list[_RefundAllocation] = []
    remaining = refund_total_cents

    for idx, it in enumerate(eligible):
        net = int(it.seller_net_cents or 0)
        if net <= 0:
            continue

        if idx == len(eligible) - 1:
            share = remaining
        else:
            share = (refund_total_cents * net) // total_net
            share = max(0, min(share, remaining))

        remaining -= share

        debit = min(share, net)
        if debit <= 0:
            continue

        allocations.append(
            _RefundAllocation(
                order_item_id=str(it.pk),
                seller_id=str(it.seller_id),
                debit_cents=int(debit),
            )
        )

    return allocations


def _maybe_mark_order_refunded(*, order: Order, refunded_total_cents: int, note: str) -> None:
    refunded_total_cents = int(refunded_total_cents or 0)
    if refunded_total_cents <= 0:
        return

    total = int(order.total_cents or 0)
    if total > 0 and refunded_total_cents < total:
        OrderEvent.objects.create(
            order=order,
            type=OrderEvent.Type.WARNING,
            message=f"Partial refund observed ({refunded_total_cents}c of {total}c). {note}",
        )
        return

    if order.status != Order.Status.REFUNDED:
        order.status = Order.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.REFUNDED, message=note)


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return HttpResponseBadRequest("Missing signature")

    try:
        event = verify_and_parse_webhook(payload, sig_header)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    stripe_event_id = (event.get("id") or "").strip()
    event_type = (event.get("type") or "").strip()
    if not stripe_event_id or not event_type:
        return HttpResponse(status=200)

    rid = (getattr(request, "request_id", "") or "").strip()

    delivery, created = StripeWebhookDelivery.objects.get_or_create(
        stripe_event_id=stripe_event_id,
        defaults={
            "event_type": event_type or "",
            "status": StripeWebhookDelivery.Status.RECEIVED,
            "request_id": rid,
        },
    )
    if not created:
        # Keep the latest request id for debugging; do not clobber status.
        if rid and delivery.request_id != rid:
            delivery.request_id = rid
            try:
                delivery.save(update_fields=["request_id"])
            except Exception:
                pass

    # Strict idempotency for business logic.
    if not _record_event_once(stripe_event_id=stripe_event_id, event_type=event_type):
        try:
            delivery.status = StripeWebhookDelivery.Status.DUPLICATE
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=["status", "processed_at"])
        except Exception:
            pass
        return HttpResponse(status=200)

    obj = (event.get("data") or {}).get("object") or {}
    order_id = _get_order_id_from_event(event)

    if not order_id and event_type == "payment_intent.payment_failed":
        payment_intent_id = (obj.get("id") or "").strip()
        if payment_intent_id:
            fallback = Order.objects.filter(stripe_payment_intent_id=payment_intent_id).first()
            if fallback:
                order_id = str(fallback.pk)

    if not order_id:
        logger.warning("Stripe event %s (%s) missing order_id mapping", stripe_event_id, event_type)
        try:
            delivery.status = StripeWebhookDelivery.Status.PROCESSED
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=["status", "processed_at"])
        except Exception:
            pass
        return HttpResponse(status=200)

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)

            if event_type == "checkout.session.completed":
                session_id = (obj.get("id") or "").strip()
                payment_intent_id = (obj.get("payment_intent") or "").strip()

                updated_fields: list[str] = []
                if session_id and not order.stripe_session_id:
                    order.stripe_session_id = session_id
                    updated_fields.append("stripe_session_id")
                if payment_intent_id and not order.stripe_payment_intent_id:
                    order.stripe_payment_intent_id = payment_intent_id
                    updated_fields.append("stripe_payment_intent_id")
                if updated_fields:
                    updated_fields.append("updated_at")
                    order.save(update_fields=updated_fields)

                # 1) Mark paid (this should also compute OrderItem snapshots/ledger fields)
                order.mark_paid(payment_intent_id=payment_intent_id, session_id=session_id)

                # 2) Save shipping snapshot if present
                ship = _extract_shipping_from_session_obj(obj)
                if any([ship["line1"], ship["city"], ship["postal_code"], ship["country"]]):
                    order.set_shipping_from_stripe(**ship)

                # 3) IMPORTANT: record SALE credits in the seller ledger BEFORE payouts
                ensure_sale_balance_entries_for_paid_order(order=order)

                # 4) Create transfers/payouts (this is where your -PAYOUT entries are created)
                create_transfers_for_paid_order(order=order, payment_intent_id=payment_intent_id)

                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            if event_type == "checkout.session.expired":
                order.mark_canceled(note="Checkout session expired")
                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            if event_type == "payment_intent.payment_failed":
                failure_message = (obj.get("last_payment_error") or {}).get("message") or "Payment failed"
                OrderEvent.objects.create(
                    order=order,
                    type=OrderEvent.Type.WARNING,
                    message=f"Payment failed (event={stripe_event_id})",
                )
                _send_order_failed_email(order, reason=failure_message)
                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            if event_type in {"charge.refunded", "refund.created", "refund.updated"}:
                refunded_cents = int(obj.get("amount_refunded") or obj.get("amount") or 0)
                payout_created = _transfers_already_created(order)

                if payout_created and refunded_cents > 0:
                    allocs = _allocate_refund_across_items(order=order, refund_total_cents=refunded_cents)

                    for a in allocs:
                        SellerBalanceEntry.objects.create(
                            seller_id=a.seller_id,
                            amount_cents=-int(a.debit_cents),
                            reason=SellerBalanceEntry.Reason.REFUND,
                            order=order,
                            order_item_id=a.order_item_id,
                            note=f"Stripe refund via {event_type} (event={stripe_event_id})",
                        )

                    OrderEvent.objects.create(
                        order=order,
                        type=OrderEvent.Type.WARNING,
                        message=(
                            f"Refund received after payout. Recorded seller debits "
                            f"(refund={refunded_cents}c, event={stripe_event_id}, type={event_type})."
                        ),
                    )
                else:
                    OrderEvent.objects.create(
                        order=order,
                        type=OrderEvent.Type.WARNING,
                        message=(
                            f"Refund received (refund={refunded_cents}c, type={event_type}, event={stripe_event_id}). "
                            f"No seller debits recorded (payout_created={payout_created})."
                        ),
                    )

                _maybe_mark_order_refunded(
                    order=order,
                    refunded_total_cents=refunded_cents,
                    note=f"Stripe refund observed ({event_type}, {refunded_cents}c, event={stripe_event_id})",
                )
                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            if event_type in {"charge.dispute.created", "charge.dispute.updated"}:
                status = (obj.get("status") or "").strip().lower()
                OrderEvent.objects.create(
                    order=order,
                    type=OrderEvent.Type.WARNING,
                    message=f"Dispute event: {event_type} status={status or 'unknown'} event={stripe_event_id}",
                )
                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            if event_type == "charge.dispute.closed":
                status = (obj.get("status") or "").strip().lower()
                payout_created = _transfers_already_created(order)

                if status == "lost":
                    if payout_created:
                        for it in order.items.all():
                            net = int(it.seller_net_cents or 0)
                            if net <= 0:
                                continue

                            SellerBalanceEntry.objects.create(
                                seller_id=str(it.seller_id),
                                amount_cents=-net,
                                reason=SellerBalanceEntry.Reason.CHARGEBACK,
                                order=order,
                                order_item=it,
                                note=f"Chargeback lost (event={stripe_event_id})",
                            )

                        OrderEvent.objects.create(
                            order=order,
                            type=OrderEvent.Type.WARNING,
                            message=(
                                "Chargeback lost. Seller debited net (payout already created). "
                                "Dispute fee may require manual adjustment."
                            ),
                        )
                    else:
                        OrderEvent.objects.create(
                            order=order,
                            type=OrderEvent.Type.WARNING,
                            message="Chargeback lost before payout. No seller debits recorded (no payout created).",
                        )

                    if order.status != Order.Status.REFUNDED:
                        order.status = Order.Status.REFUNDED
                        order.save(update_fields=["status", "updated_at"])
                        OrderEvent.objects.create(order=order, type=OrderEvent.Type.REFUNDED, message="Chargeback lost")

                    try:
                        delivery.status = StripeWebhookDelivery.Status.PROCESSED
                        delivery.processed_at = timezone.now()
                        delivery.save(update_fields=["status", "processed_at"])
                    except Exception:
                        pass
                    return HttpResponse(status=200)

                OrderEvent.objects.create(
                    order=order,
                    type=OrderEvent.Type.WARNING,
                    message=f"Chargeback closed with status={status or 'unknown'} event={stripe_event_id}",
                )
                try:
                    delivery.status = StripeWebhookDelivery.Status.PROCESSED
                    delivery.processed_at = timezone.now()
                    delivery.save(update_fields=["status", "processed_at"])
                except Exception:
                    pass
                return HttpResponse(status=200)

            try:
                delivery.status = StripeWebhookDelivery.Status.PROCESSED
                delivery.processed_at = timezone.now()
                delivery.save(update_fields=["status", "processed_at"])
            except Exception:
                pass
            return HttpResponse(status=200)

    except Order.DoesNotExist:
        try:
            delivery.status = StripeWebhookDelivery.Status.PROCESSED
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=["status", "processed_at"])
        except Exception:
            pass
        return HttpResponse(status=200)
    except Exception as e:
        logger.exception(
            "Stripe webhook processing failed event=%s type=%s order=%s",
            stripe_event_id,
            event_type,
            order_id,
        )
        try:
            delivery.status = StripeWebhookDelivery.Status.ERROR
            delivery.error_message = (str(e) or "Webhook processing failed")[:2000]
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=["status", "error_message", "processed_at"])
        except Exception:
            pass
        # IMPORTANT: return 500 so Stripe will retry.
        return HttpResponse(status=500)
