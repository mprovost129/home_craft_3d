# payments/services.py

from __future__ import annotations

from django.db.models import Sum

from payments.models import SellerBalanceEntry


def get_seller_balance_cents(*, seller) -> int:
    """
    Returns signed balance.
    Negative => seller owes platform.
    """
    agg = SellerBalanceEntry.objects.filter(seller=seller).aggregate(
        total=Sum("amount_cents")
    )
    return int(agg["total"] or 0)
