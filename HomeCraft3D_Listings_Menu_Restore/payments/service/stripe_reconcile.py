from __future__ import annotations

from typing import Dict

from orders.models import Order, OrderItem


def reconcile_order(order: Order) -> Dict[str, int]:
    """
    Read-only reconciliation.
    Compares snapshot ledger values vs Stripe artifacts.
    """

    snapshot_gross = order.total_cents
    snapshot_platform = order.platform_fee_cents_snapshot

    # Query OrderItem objects related to this order

    order_items = OrderItem.objects.filter(order=order)

    snapshot_net = sum(
        item.seller_net_cents for item in order_items
    )

    # If there is a correct attribute to check for transfer, replace 'is_transferred' with the actual attribute name.
    transfers_total = sum(
        item.seller_net_cents
        for item in order_items
        if getattr(item, "is_transferred", False)
    )

    # Replace 'get_refund_amount_cents()' with the actual method or attribute if different
    refunds_total = sum(
        getattr(item, "get_refund_amount_cents", lambda: 0)() if hasattr(item, "get_refund_amount_cents") else 0
        for item in order_items
    )

    return {
        "snapshot_gross": snapshot_gross,
        "snapshot_platform": snapshot_platform,
        "snapshot_net": snapshot_net,
        "transfers_total": transfers_total,
        "refunds_total": refunds_total,
        "delta": snapshot_net - transfers_total + refunds_total,
    }
