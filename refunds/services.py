# refunds/services.py

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.template.loader import render_to_string
from django.conf import settings

from orders.models import Order, OrderEvent, OrderItem, _absolute_static_url, _site_base_url
from products.permissions import is_owner_user

from .models import AllocatedLineRefund, RefundRequest
from .stripe_service import create_stripe_refund_for_request

logger = logging.getLogger(__name__)


def _buyer_email_for_refund(rr: RefundRequest) -> str:
    if rr.buyer and rr.buyer.email:
        return rr.buyer.email
    if rr.requester_email:
        return rr.requester_email
    if rr.order and rr.order.guest_email:
        return rr.order.guest_email
    return ""


def _seller_email_for_refund(rr: RefundRequest) -> str:
    seller = getattr(rr, "seller", None)
    if seller and getattr(seller, "email", None):
        return seller.email
    return ""


def _order_link_for_refund(rr: RefundRequest, base: str) -> str:
    order = rr.order
    link = f"{base}{reverse('orders:detail', kwargs={'order_id': order.pk})}"
    if order.is_guest:
        link = f"{link}?t={order.order_token}"
    return link


def _seller_order_link(rr: RefundRequest, base: str) -> str:
    return f"{base}{reverse('orders:seller_order_detail', kwargs={'order_id': rr.order.pk})}"


def _format_cents(cents: int) -> str:
    return f"${(int(cents or 0) / 100.0):.2f}"


def _send_refund_requested_email(rr: RefundRequest) -> None:
    recipient = _seller_email_for_refund(rr)
    if not recipient:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _seller_order_link(rr, base)

    item_title = getattr(rr.order_item.product, "title", "Item")
    refund_amount = _format_cents(rr.total_refund_cents_snapshot)

    subject = f"Refund requested for order #{rr.order.pk}"
    body = "\n".join(
        [
            f"Refund requested for {item_title}.",
            f"Amount: {refund_amount}",
            "",
            "View request:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/refund_requested.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": rr.order.pk,
            "item_title": item_title,
            "refund_amount": refund_amount,
            "order_link": order_link,
            "reason": rr.get_reason_display(),
            "notes": rr.notes,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_refund_decision_email(rr: RefundRequest) -> None:
    recipient = _buyer_email_for_refund(rr)
    if not recipient:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _order_link_for_refund(rr, base)

    item_title = getattr(rr.order_item.product, "title", "Item")
    refund_amount = _format_cents(rr.total_refund_cents_snapshot)

    approved = rr.status == RefundRequest.Status.APPROVED
    subject = (
        f"Refund approved for order #{rr.order.pk}" if approved else f"Refund declined for order #{rr.order.pk}"
    )

    template = "emails/refund_approved.html" if approved else "emails/refund_declined.html"

    body = "\n".join(
        [
            f"Refund decision for {item_title}.",
            f"Amount: {refund_amount}",
            "",
            "View order:",
            order_link,
        ]
    )

    html_message = render_to_string(
        template,
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": rr.order.pk,
            "item_title": item_title,
            "refund_amount": refund_amount,
            "order_link": order_link,
            "decision_note": rr.seller_decision_note,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient],
            html_message=html_message,
        )
    except Exception:
        pass


def _send_refund_processed_email(rr: RefundRequest) -> None:
    recipient = _buyer_email_for_refund(rr)
    if not recipient:
        return

    base = _site_base_url()
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")
    order_link = _order_link_for_refund(rr, base)

    item_title = getattr(rr.order_item.product, "title", "Item")
    refund_amount = _format_cents(rr.total_refund_cents_snapshot)

    subject = f"Refund processed for order #{rr.order.pk}"
    body = "\n".join(
        [
            f"Your refund for {item_title} has been processed.",
            f"Amount: {refund_amount}",
            "",
            "View order:",
            order_link,
        ]
    )

    html_message = render_to_string(
        "emails/refund_processed.html",
        {
            "subject": subject,
            "logo_url": logo_url,
            "order_id": rr.order.pk,
            "item_title": item_title,
            "refund_amount": refund_amount,
            "order_link": order_link,
        },
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient],
            html_message=html_message,
        )
    except Exception:
        pass


# ============================================================
# Allocation helpers
# ============================================================
def _safe_int(x) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def _allocate_tax_for_item(*, order: Order, item: OrderItem) -> int:
    """
    Allocate order.tax_cents proportionally across ALL order items by line_total.
    """
    total_tax = _safe_int(order.tax_cents)
    if total_tax <= 0:
        return 0

    items = list(order.items.all())
    if not items:
        return 0

    denom = sum(_safe_int(i.line_total_cents) for i in items)
    if denom <= 0:
        return 0

    share = Decimal(_safe_int(item.line_total_cents)) / Decimal(denom)
    alloc = (Decimal(total_tax) * share).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, int(alloc))


def _allocate_shipping_for_item(*, order: Order, item: OrderItem) -> int:
    """
    Allocate order.shipping_cents across shippable (requires_shipping=True) items by line_total.
    """
    total_shipping = _safe_int(order.shipping_cents)
    if total_shipping <= 0:
        return 0

    shippable = [i for i in order.items.all() if bool(getattr(i, "requires_shipping", False))]
    if not shippable:
        return 0

    denom = sum(_safe_int(i.line_total_cents) for i in shippable)
    if denom <= 0:
        return 0

    share = Decimal(_safe_int(item.line_total_cents)) / Decimal(denom)
    alloc = (Decimal(total_shipping) * share).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, int(alloc))


def compute_allocated_line_refund(*, order: Order, item: OrderItem) -> AllocatedLineRefund:
    """
    FULL refund per physical line item:
      - line subtotal = item.line_total_cents
      - plus allocated tax
      - plus allocated shipping (only across shippable lines)
    """
    line_subtotal = _safe_int(item.line_total_cents)
    tax_alloc = _allocate_tax_for_item(order=order, item=item)
    ship_alloc = _allocate_shipping_for_item(order=order, item=item)

    total = max(0, line_subtotal + tax_alloc + ship_alloc)

    return AllocatedLineRefund(
        line_subtotal_cents=line_subtotal,
        tax_cents_allocated=tax_alloc,
        shipping_cents_allocated=ship_alloc,
        total_refund_cents=total,
    )


# ============================================================
# Core service functions
# ============================================================
@transaction.atomic
def create_refund_request(
    *,
    order: Order,
    item: OrderItem,
    requester_user,
    requester_email: str,
    reason: str,
    notes: str = "",
) -> RefundRequest:
    """
    Create a refund request for a PAID order + PHYSICAL line item only.
    One refund request per item (OneToOne).
    """
    if order.pk != item.order_id:
        raise ValidationError("Order item does not belong to this order.")

    if order.status != Order.Status.PAID or not getattr(order, "paid_at", None):
        raise ValidationError("Refund requests are available only for paid orders.")

    # Physical-only enforcement (locked spec)
    if bool(getattr(item, "is_digital", False)) or not bool(getattr(item, "requires_shipping", False)):
        raise ValidationError("Refund requests are only allowed for physical items.")

    # Seller snapshot must exist
    if not getattr(item, "seller_id", None):
        raise ValidationError("Order item is missing seller snapshot.")

    # One per item (reverse OneToOne raises DoesNotExist)
    try:
        _ = item.refund_request
        raise ValidationError("A refund request already exists for this item.")
    except RefundRequest.DoesNotExist:
        pass
    except Exception:
        raise ValidationError("Unable to verify existing refund status for this item.")

    alloc = compute_allocated_line_refund(order=order, item=item)

    rr = RefundRequest.objects.create(
        order=order,
        order_item=item,
        seller_id=item.seller_id,
        buyer_id=getattr(order, "buyer_id", None) or None,
        requester_email=(requester_email or "").strip().lower(),
        reason=reason,
        notes=(notes or "").strip(),
        status=RefundRequest.Status.REQUESTED,
        line_subtotal_cents_snapshot=_safe_int(alloc.line_subtotal_cents),
        tax_cents_allocated_snapshot=_safe_int(alloc.tax_cents_allocated),
        shipping_cents_allocated_snapshot=_safe_int(alloc.shipping_cents_allocated),
        total_refund_cents_snapshot=_safe_int(alloc.total_refund_cents),
    )

    rr.full_clean()
    rr.save(update_fields=["updated_at"])

    try:
        OrderEvent.objects.create(
            order=order,
            type=OrderEvent.Type.WARNING,
            message=f"Refund requested rr={rr.pk} item={item.pk} seller={item.seller_id}",
        )
    except Exception:
        pass

    _send_refund_requested_email(rr)

    return rr


@transaction.atomic
def seller_decide(*, rr: RefundRequest, seller_user, approve: bool, note: str = "") -> RefundRequest:
    """
    Seller (or owner/staff) approves/declines.
    """
    if rr.status != RefundRequest.Status.REQUESTED:
        raise ValidationError("This refund request is not awaiting a decision.")

    if not seller_user or not getattr(seller_user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    # allow seller themselves, owner, or staff/superuser
    if not (
        is_owner_user(seller_user)
        or bool(getattr(seller_user, "is_staff", False))
        or bool(getattr(seller_user, "is_superuser", False))
    ):
        if rr.seller_id != seller_user.id:
            raise PermissionDenied("You do not have permission to decide this refund request.")

    rr.status = RefundRequest.Status.APPROVED if approve else RefundRequest.Status.DECLINED
    rr.seller_decided_at = timezone.now()
    rr.seller_decision_note = (note or "").strip()
    rr.save(update_fields=["status", "seller_decided_at", "seller_decision_note", "updated_at"])

    try:
        OrderEvent.objects.create(
            order=rr.order,
            type=OrderEvent.Type.WARNING,
            message=f"Refund {rr.status} rr={rr.pk} by={seller_user.pk}",
        )
    except Exception:
        pass

    _send_refund_decision_email(rr)

    return rr


@transaction.atomic
def trigger_refund(*, rr: RefundRequest, actor_user, allow_staff_safety_valve: bool = True) -> RefundRequest:
    """
    Trigger the Stripe refund after approval.
    - Uses rr.total_refund_cents_snapshot as the source of truth.
    """
    if rr.status != RefundRequest.Status.APPROVED:
        raise ValidationError("Refund must be approved before it can be processed.")

    if not rr.is_refundable_now:
        raise ValidationError("This refund is not refundable right now.")

    if not actor_user or not getattr(actor_user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    is_staff = bool(getattr(actor_user, "is_staff", False) or getattr(actor_user, "is_superuser", False))
    is_owner = is_owner_user(actor_user)

    if rr.seller_id == actor_user.id:
        pass
    elif is_owner:
        pass
    elif allow_staff_safety_valve and is_staff:
        pass
    else:
        raise PermissionDenied("You do not have permission to process this refund.")

    refund_id = create_stripe_refund_for_request(rr=rr)

    rr.stripe_refund_id = refund_id
    rr.refunded_at = timezone.now()
    rr.status = RefundRequest.Status.REFUNDED
    rr.save(update_fields=["stripe_refund_id", "refunded_at", "status", "updated_at"])

    try:
        OrderEvent.objects.create(
            order=rr.order,
            type=OrderEvent.Type.REFUNDED,
            message=f"Refund processed rr={rr.pk} stripe_refund={refund_id}",
        )
    except Exception:
        pass

    _send_refund_processed_email(rr)

    return rr
