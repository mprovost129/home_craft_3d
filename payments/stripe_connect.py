# payments/stripe_connect.py
from __future__ import annotations

import stripe
from django.conf import settings
from django.urls import reverse


def _base_url() -> str:
    if not (base := (getattr(settings, "SITE_BASE_URL", "") or "").strip()):
        raise RuntimeError("SITE_BASE_URL is required for Stripe Connect links.")
    else:
        return base.rstrip("/")


def configure_stripe() -> None:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_express_account(*, email: str, country: str = "US") -> stripe.Account:
    configure_stripe()

    return stripe.Account.create(
        type="express",
        country=country,
        email=email,
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        business_type="individual",  # MVP default; Stripe will ask for details
    )


def create_account_link(*, stripe_account_id: str) -> stripe.AccountLink:
    """
    Returns a Stripe-hosted onboarding link for an Express account.
    """
    configure_stripe()

    refresh_url = f"{_base_url()}{reverse('payments:connect_refresh')}"
    return_url = f"{_base_url()}{reverse('payments:connect_return')}"

    return stripe.AccountLink.create(
        account=stripe_account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )


def retrieve_account(stripe_account_id: str) -> stripe.Account:
    configure_stripe()
    return stripe.Account.retrieve(stripe_account_id)
