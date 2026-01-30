from __future__ import annotations

from payments.models import SellerStripeAccount
from products.permissions import is_owner_user


def seller_is_stripe_ready(seller_user) -> bool:
    """
    True if seller can receive payouts (Stripe Connect fully enabled).

    Owner/admin bypass is treated as ready.
    """
    if seller_user and is_owner_user(seller_user):
        return True

    acct = SellerStripeAccount.objects.filter(user=seller_user).first()
    return bool(acct and acct.is_ready)
