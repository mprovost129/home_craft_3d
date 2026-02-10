# payments/services.py

from __future__ import annotations

from collections import defaultdict

from django.db.models import Sum

from payments.models import SellerBalanceEntry


def get_seller_balance_cents(*, seller) -> int:
    """
    Returns signed balance from SellerBalanceEntry ledger.

    Positive => platform owes seller
    Negative => seller owes platform
    """
    agg = SellerBalanceEntry.objects.filter(seller=seller).aggregate(
        total=Sum("amount_cents")
    )
    return int(agg["total"] or 0)


def ensure_sale_balance_entries_for_paid_order(*, order) -> None:
    """
    Ensure there is a +SALE ledger credit for each seller in a PAID order.

    This is idempotent via the (seller, order, reason) uniqueness constraint.
    """
    # We assume order.items exist and each item has seller_id + seller_net_cents snapshot.
    totals_by_seller: dict[str, int] = defaultdict(int)

    for it in order.items.all():
        seller_id = getattr(it, "seller_id", None)
        if not seller_id:
            continue
        net = int(getattr(it, "seller_net_cents", 0) or 0)
        if net <= 0:
            continue
        totals_by_seller[str(seller_id)] += net

    for seller_id, net_cents in totals_by_seller.items():
        if net_cents <= 0:
            continue

        # One SALE credit per seller per order
        SellerBalanceEntry.objects.get_or_create(
            seller_id=seller_id,
            order=order,
            reason=SellerBalanceEntry.Reason.SALE,
            defaults={
                "amount_cents": int(net_cents),
                "note": f"Order paid: credit seller net for order {order.pk}",
            },
        )
