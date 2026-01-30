from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from orders.models import Order, OrderItem


def get_reviewable_order_item_or_403(*, user, order_item_id: int) -> OrderItem:
    """
    MVP: Only authenticated buyers can review items from their PAID orders.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Login required.")

    item = get_object_or_404(
        OrderItem.objects.select_related("order", "product"),
        pk=order_item_id,
    )

    order: Order = item.order

    if order.status != Order.Status.PAID:
        raise PermissionDenied("Order is not paid.")

    if not order.buyer_id or order.buyer_id != user.id:
        raise PermissionDenied("You do not have access to review this item.")

    # Enforce one review per order_item via OneToOne; caller can check existence
    return item
