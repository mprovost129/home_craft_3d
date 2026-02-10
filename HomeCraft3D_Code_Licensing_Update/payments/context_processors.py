# payments/context_processors.py
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

from payments.models import SellerStripeAccount
from products.permissions import is_owner_user, is_seller_user


def seller_stripe_status(request):
    """Global template context.

    - seller_stripe_ready: True/False/None
        None => not a seller (hide badge)
    - has_connect_sync: bool (payments:connect_sync exists)
    - user_is_owner: bool (owner/admin override)
    - user_is_seller: bool (seller OR owner/admin)

    Notes:
    - These flags avoid templates touching `user.profile` directly, which can raise
      RelatedObjectDoesNotExist if a Profile row isn't created yet.
    """
    user = getattr(request, "user", None)

    user_is_owner = False
    user_is_seller = False
    seller_stripe_ready = None

    if user and getattr(user, "is_authenticated", False):
        user_is_owner = is_owner_user(user)
        user_is_seller = is_seller_user(user)

        if user_is_owner:
            seller_stripe_ready = True
        elif user_is_seller:
            acct = SellerStripeAccount.objects.filter(user=user).first()
            seller_stripe_ready = bool(acct and acct.is_ready)

    try:
        reverse("payments:connect_sync")
        has_connect_sync = True
    except NoReverseMatch:
        has_connect_sync = False

    return {
        "seller_stripe_ready": seller_stripe_ready,
        "has_connect_sync": has_connect_sync,
        "user_is_owner": user_is_owner,
        "user_is_seller": user_is_seller,
    }
