# cart/cart.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from products.models import Product

CART_SESSION_KEY = "hc3_cart_v1"


def _to_decimal_money(value: Any) -> Decimal:
    """
    Convert user/session value to a safe Decimal dollars amount.
    Always returns >= 0.00.
    """
    if value is None:
        return Decimal("0.00")

    if isinstance(value, Decimal):
        d = value
    else:
        s = str(value).strip()
        if not s:
            return Decimal("0.00")
        # allow "$12.34" style input
        s = s.replace("$", "").replace(",", "").strip()
        try:
            d = Decimal(s)
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    if d.is_nan() or d.is_infinite():
        return Decimal("0.00")

    if d < 0:
        return Decimal("0.00")

    # currency-safe rounding to cents
    return d.quantize(Decimal("0.01"))


def product_unit_price(product: Product) -> Decimal:
    # Free items are always 0.00
    if getattr(product, "is_free", False):
        return Decimal("0.00")
    return _to_decimal_money(getattr(product, "price", "0.00"))


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int
    buyer_notes: str = ""
    tip_amount: Decimal = Decimal("0.00")

    @property
    def is_tip(self) -> bool:
        return bool(self.tip_amount and self.tip_amount > 0)

    @property
    def unit_price(self) -> Decimal:
        return product_unit_price(self.product)

    @property
    def line_total(self) -> Decimal:
        # Product total only (tips shown separately)
        return (self.unit_price * Decimal(int(self.quantity or 0))).quantize(Decimal("0.01"))

    @property
    def tip_total(self) -> Decimal:
        # Tip is always a single amount per product line (not multiplied by quantity)
        return _to_decimal_money(self.tip_amount)


class Cart:
    """
    Session-backed cart.

    Session format:
      {
        "<product_id>": {
            "qty": 2,
            "notes": "optional",
            "tip": "5.00"   # string dollars (optional)
        }
      }
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        raw = self.session.get(CART_SESSION_KEY, {})
        self.data: Dict[str, Dict[str, Any]] = raw if isinstance(raw, dict) else {}

    def _save(self) -> None:
        self.session[CART_SESSION_KEY] = self.data
        self.session.modified = True

    def clear(self) -> None:
        self.data = {}
        self._save()

    def add(
        self,
        product: Product,
        quantity: int = 1,
        buyer_notes: str = "",
        is_tip: bool = False,
        tip_amount: Any = "0.00",
    ) -> None:
        if not getattr(product, "is_active", False):
            return

        pid = str(product.pk)

        # Digital files forced to qty=1
        try:
            if product.kind == Product.Kind.FILE:
                quantity = 1
        except Exception:
            pass

        quantity = max(int(quantity or 1), 1)
        notes = (buyer_notes or "").strip()

        tip_dec = _to_decimal_money(tip_amount) if is_tip else Decimal("0.00")

        if pid in self.data:
            payload = self.data[pid]
            # quantity accumulation for physical only
            try:
                if product.kind == Product.Kind.FILE:
                    payload["qty"] = 1
                else:
                    payload["qty"] = max(1, int(payload.get("qty", 1)) + quantity)
            except Exception:
                payload["qty"] = max(1, int(payload.get("qty", 1)) + quantity)

            # notes: only overwrite when provided
            if notes:
                payload["notes"] = notes

            # tip: overwrite if provided & > 0
            if tip_dec > 0:
                payload["tip"] = str(tip_dec)
            # do not auto-clear tip here; use set_tip()
            self.data[pid] = payload
        else:
            payload: Dict[str, Any] = {"qty": quantity}
            if notes:
                payload["notes"] = notes
            if tip_dec > 0:
                payload["tip"] = str(tip_dec)
            self.data[pid] = payload

        self._save()

    def set_quantity(self, product: Product, quantity: int) -> None:
        pid = str(product.pk)
        if pid not in self.data:
            return

        try:
            if product.kind == Product.Kind.FILE:
                self.data[pid]["qty"] = 1
            else:
                q = int(quantity)
                if q <= 0:
                    self.remove(product)
                    return
                self.data[pid]["qty"] = q
        except Exception:
            q = int(quantity or 1)
            if q <= 0:
                self.remove(product)
                return
            self.data[pid]["qty"] = q

        self._save()

    def set_notes(self, product: Product, buyer_notes: str) -> None:
        pid = str(product.pk)
        if pid not in self.data:
            return

        notes = (buyer_notes or "").strip()
        if notes:
            self.data[pid]["notes"] = notes
        else:
            self.data[pid].pop("notes", None)

        self._save()

    def set_tip(self, product: Product, tip_amount: Any) -> None:
        """
        Set or clear a tip for a product line.
        - empty/0 => clears
        - >0 => stores as string dollars
        """
        pid = str(product.pk)
        if pid not in self.data:
            return

        d = _to_decimal_money(tip_amount)
        if d <= 0:
            self.data[pid].pop("tip", None)
        else:
            self.data[pid]["tip"] = str(d)

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
                del self.data[pid_str]
                dirty = True
                continue

            product = by_id.get(pid)
            if not product:
                # deleted or inactive -> remove
                del self.data[pid_str]
                dirty = True
                continue

            qty = int(payload.get("qty", 1) or 1)

            # Digital files forced to qty=1
            try:
                if product.kind == Product.Kind.FILE:
                    qty = 1
            except Exception:
                pass

            qty = max(1, qty)

            notes = str(payload.get("notes", "") or "")
            tip = _to_decimal_money(payload.get("tip", "0.00"))

            result.append(
                CartLine(
                    product=product,
                    quantity=qty,
                    buyer_notes=notes,
                    tip_amount=tip,
                )
            )

        if dirty:
            self._save()

        return result

    def items_subtotal(self) -> Decimal:
        """
        Product totals only (no tips).
        """
        total = Decimal("0.00")
        for line in self.lines():
            total += line.line_total
        return total.quantize(Decimal("0.01"))

    def tips_total(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.lines():
            total += line.tip_total
        return total.quantize(Decimal("0.01"))

    def grand_total(self) -> Decimal:
        return (self.items_subtotal() + self.tips_total()).quantize(Decimal("0.01"))

    def subtotal(self) -> Decimal:
        """
        Backwards-compatible: keep name subtotal() but return product subtotal (no tips).
        Your template/view can show tips separately + grand total.
        """
        return self.items_subtotal()

    def count_items(self) -> int:
        # count distinct product lines
        return len(self.data)
