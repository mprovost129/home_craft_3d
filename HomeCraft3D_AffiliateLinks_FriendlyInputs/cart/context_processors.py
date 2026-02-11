# cart/context_processors.py
from __future__ import annotations

from .cart import Cart


def cart_summary(request):
    cart = Cart(request)
    try:
        count = sum(line.quantity for line in cart.lines())
    except Exception:
        count = 0
    return {"cart_item_count": count}
