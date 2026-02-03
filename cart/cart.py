# cart/cart.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from products.models import Product

CART_SESSION_KEY = "hc3_cart_v1"


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int

    @property
    def unit_price(self) -> Decimal:
        return product_unit_price(self.product)

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


def product_unit_price(product: Product) -> Decimal:
    # Free items are always 0.00
    if getattr(product, "is_free", False):
        return Decimal("0.00")
    return Decimal(str(getattr(product, "price", "0.00")))


class Cart:
    """
    Session-backed cart.
    Data format in session:
      {
        "<product_id>": {"qty": 1}
      }
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.data: Dict[str, Dict[str, int]] = self.session.get(CART_SESSION_KEY, {})

    def _save(self) -> None:
        self.session[CART_SESSION_KEY] = self.data
        self.session.modified = True

    def clear(self) -> None:
        self.data = {}
        self._save()

    def add(self, product: Product, quantity: int = 1) -> None:
        if not product.is_active:
            return

        pid = str(product.pk)

        # Digital files forced to qty=1
        if product.kind == Product.Kind.FILE:
            quantity = 1

        quantity = max(int(quantity), 1)

        if pid in self.data:
            if product.kind == Product.Kind.FILE:
                self.data[pid]["qty"] = 1
            else:
                self.data[pid]["qty"] = max(1, int(self.data[pid]["qty"]) + quantity)
        else:
            self.data[pid] = {"qty": quantity}

        self._save()

    def set_quantity(self, product: Product, quantity: int) -> None:
        pid = str(product.pk)
        if pid not in self.data:
            return

        if product.kind == Product.Kind.FILE:
            self.data[pid]["qty"] = 1
        else:
            q = int(quantity)
            if q <= 0:
                self.remove(product)
                return
            self.data[pid]["qty"] = q

        self._save()

    def remove(self, product: Product) -> None:
        pid = str(product.pk)
        if pid in self.data:
            del self.data[pid]
            self._save()

    def product_ids(self) -> List[int]:
        ids: List[int] = []
        for k in self.data.keys():
            try:
                ids.append(int(k))
            except ValueError:
                continue
        return ids

    def lines(self) -> List[CartLine]:
        ids = self.product_ids()

        products = (
            Product.objects.filter(pk__in=ids, is_active=True)
            .select_related("category", "seller")
            .prefetch_related("images")
        )
        by_id = {p.pk: p for p in products}

        result: List[CartLine] = []
        dirty = False

        for pid_str, payload in list(self.data.items()):
            try:
                pid = int(pid_str)
            except ValueError:
                # invalid key in session -> drop
                del self.data[pid_str]
                dirty = True
                continue

            product = by_id.get(pid)
            if not product:
                # product no longer active or deleted -> drop it from session
                del self.data[pid_str]
                dirty = True
                continue

            qty = int(payload.get("qty", 1))

            if product.kind == Product.Kind.FILE:
                qty = 1
            else:
                qty = max(1, qty)

            result.append(CartLine(product=product, quantity=qty))

        if dirty:
            self._save()

        return result

    def subtotal(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.lines():
            total += line.line_total
        return total

    def count_items(self) -> int:
        # count distinct lines, not quantities
        return len(self.data)
