from __future__ import annotations

from payments.models import SellerStripeAccount
from products.permissions import is_owner_user


def seller_stripe_status(request):
    """
    Expose seller Stripe status globally (navbar, dashboards, etc).

    Safe defaults:
    - Non-auth users: nothing
    - Non-sellers: nothing
    - Owner/admin: treated as Stripe-ready
    """
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {}

    if is_owner_user(user):
        return {
            "seller_stripe_ready": True,
            "seller_stripe_account": None,
        }

    acct = SellerStripeAccount.objects.filter(user=user).first()
    if not acct:
        return {
            "seller_stripe_ready": False,
            "seller_stripe_account": None,
        }

    return {
        "seller_stripe_ready": acct.is_ready,
        "seller_stripe_account": acct,
    }
