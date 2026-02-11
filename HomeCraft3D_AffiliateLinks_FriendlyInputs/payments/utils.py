# payments/utils.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

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


MoneyLike = Union[Decimal, int, float, str, None]


def money_to_cents(value: MoneyLike) -> int:
    """Convert a currency amount (e.g. dollars) to integer cents safely.

    Accepts Decimal, int, float, or numeric string. Uses ROUND_HALF_UP.

    NOTE:
    - If caller passes an int, we assume it is already cents (by convention).
    """
    if value is None:
        return 0

    if isinstance(value, int):
        return int(value)

    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    cents = (dec * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def cents_to_money(cents: int) -> Decimal:
    return (Decimal(int(cents)) / Decimal("100")).quantize(Decimal("0.01"))
