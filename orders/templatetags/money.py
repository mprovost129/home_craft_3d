from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter(name="cents_to_dollars")
def cents_to_dollars(value) -> str:
    """
    12345 -> "123.45"
    Safely formats cents as dollars for display.
    """
    try:
        cents = int(value or 0)
    except (TypeError, ValueError):
        cents = 0

    dollars = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{dollars}"
