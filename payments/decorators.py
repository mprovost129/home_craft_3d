# payments/decorators.py

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from products.permissions import is_owner_user
from payments.models import SellerStripeAccount


def stripe_ready_required(view_func):
    """
    Gate seller uploads/publishing until Stripe Connect is fully enabled.

    Owner/admin bypasses the gate.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and is_owner_user(request.user):
            return view_func(request, *args, **kwargs)

        acct = SellerStripeAccount.objects.filter(user=request.user).first()
        if not acct or not acct.is_ready:
            messages.warning(
                request,
                "You must finish Stripe onboarding before you can create or modify listings.",
            )
            return redirect("payments:connect_status")

        return view_func(request, *args, **kwargs)

    return _wrapped
