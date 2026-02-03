from __future__ import annotations

from django.core.exceptions import PermissionDenied

from orders.models import Order, OrderItem


def get_reviewable_order_item_or_403(*, user, order_item_id: int) -> OrderItem:
    """Return an OrderItem the user is allowed to review, else raise PermissionDenied.

    Rules:
    - User must be authenticated.
    - OrderItem must exist.
    - The parent order must be PAID.
    - The order's buyer must be the requesting user.

    Notes:
    - One review per OrderItem is enforced in models via OneToOneField.
    """

    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required")

    item = (
        OrderItem.objects.select_related("order", "product")
        .filter(id=order_item_id)
        .first()
    )
    if not item:
        raise PermissionDenied("Order item not found")

    order = item.order
    if not order or order.status != Order.Status.PAID:
        raise PermissionDenied("Order not paid")

    if getattr(order, "buyer_id", None) != getattr(user, "id", None):
        raise PermissionDenied("Not your order")

    return item


def get_rateable_seller_order_or_403(*, user, order_id: int, seller_id: int) -> Order:
    """Return an Order the user can use to rate a seller, else raise PermissionDenied.

    Rules:
    - User must be authenticated.
    - Order must exist and be PAID.
    - Order.buyer must be the requesting user.
    - Order must include at least one OrderItem with product.seller_id == seller_id.
    """

    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required")

    order = Order.objects.filter(id=order_id).first()
    if not order:
        raise PermissionDenied("Order not found")

    if order.status != Order.Status.PAID:
        raise PermissionDenied("Order not paid")

    if getattr(order, "buyer_id", None) != getattr(user, "id", None):
        raise PermissionDenied("Not your order")

    has_seller_item = (
        OrderItem.objects.filter(order_id=order.id, product__seller_id=seller_id)
        .exists()
    )
    if not has_seller_item:
        raise PermissionDenied("Seller not in this order")

    return order