from __future__ import annotations

from typing import Any

from payments.models import SellerStripeAccount
from products.permissions import is_owner_user, is_seller_user


def sidebar_flags(request) -> dict[str, Any]:
    """
    Global sidebar flags used by templates/partials/sidebar_dashboard.html.

    Keeps dashboards templates stable (no need to remember passing these in every view).
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "user_is_owner": False,
            "user_is_seller": False,
            "seller_stripe_ready": None,
        }

    owner = bool(is_owner_user(user))
    seller = bool(is_seller_user(user))

    # Only compute readiness if they're a seller (or owner who can see seller areas).
    # Owner may not have a SellerStripeAccount, so keep it None in that case.
    stripe_ready = None
    if seller:
        acct = SellerStripeAccount.objects.filter(user=user).only(
            "stripe_account_id",
            "details_submitted",
            "charges_enabled",
            "payouts_enabled",
        ).first()
        stripe_ready = bool(acct.is_ready) if acct else False

    return {
        "user_is_owner": owner,
        "user_is_seller": seller,
        "seller_stripe_ready": stripe_ready,
    }
