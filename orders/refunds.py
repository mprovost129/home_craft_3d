# orders/refunds.py

from __future__ import annotations

from typing import Iterable

from django.db import transaction

from orders.models import Order, OrderItem, OrderEvent
from payments.models import SellerBalanceEntry


@transaction.atomic
def refund_order_items(
    *,
    order: Order,
    items: Iterable[OrderItem],
    reason: str,
    refund_marketplace_fee: bool = False,
) -> None:
    """
    Refunds specific order items.

    Assumptions:
    - Stripe refund is handled upstream (this function is ledger + audit only)
    - Items belong to the given order
    """
    if order.status not in {Order.Status.PAID, Order.Status.REFUNDED}:
        raise ValueError("Cannot refund an unpaid order.")

    items_list = list(items)

    for item in items_list:
        if item.order_id != order.id:
            raise ValueError("OrderItem does not belong to this order.")

        SellerBalanceEntry.objects.create(
            seller=item.seller,
            amount_cents=-int(item.seller_net_cents),
            reason=SellerBalanceEntry.Reason.REFUND,
            order=order,
            order_item=item,
            note=reason,
        )

        if refund_marketplace_fee and int(item.marketplace_fee_cents or 0) > 0:
            SellerBalanceEntry.objects.create(
                seller=item.seller,
                amount_cents=int(item.marketplace_fee_cents),
                reason=SellerBalanceEntry.Reason.ADJUSTMENT,
                order=order,
                order_item=item,
                note="Marketplace fee refunded",
            )

    OrderEvent.objects.create(
        order=order,
        type=OrderEvent.Type.REFUNDED,
        message=reason,
    )

    if len(items_list) == order.items.count():
        order.status = Order.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
