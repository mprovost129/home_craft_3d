from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.models import Product, ProductEngagementEvent
from .cart import Cart
from .forms import AddToCartForm, UpdateCartLineForm


def cart_detail(request):
    cart = Cart(request)
    lines = cart.lines()
    subtotal = cart.subtotal()

    update_forms = []
    for line in lines:
        update_forms.append(
            UpdateCartLineForm(
                initial={"product_id": line.product.pk, "quantity": line.quantity}
            )
        )

    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart_lines": lines,
            "subtotal": subtotal,
            "update_forms": update_forms,
        },
    )


@require_POST
def cart_add(request):
    form = AddToCartForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not add item to cart.")
        return redirect("cart:detail")

    product = get_object_or_404(Product, pk=form.cleaned_data["product_id"], is_active=True)
    qty = form.cleaned_data.get("quantity") or 1

    cart = Cart(request)
    cart.add(product, quantity=qty)

    # Engagement event (best-effort)
    try:
        ProductEngagementEvent.objects.create(
            product=product,
            event_type=ProductEngagementEvent.EventType.ADD_TO_CART,
        )
    except Exception:
        pass

    messages.success(request, "Added to cart.")
    return redirect("cart:detail")


@require_POST
def cart_update(request):
    form = UpdateCartLineForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not update cart.")
        return redirect("cart:detail")

    product = get_object_or_404(Product, pk=form.cleaned_data["product_id"])
    qty = form.cleaned_data["quantity"]

    cart = Cart(request)
    cart.set_quantity(product, qty)

    messages.success(request, "Cart updated.")
    return redirect("cart:detail")


@require_POST
def cart_remove(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id)

    cart = Cart(request)
    cart.remove(product)

    messages.success(request, "Removed from cart.")
    return redirect("cart:detail")


@require_POST
def cart_clear(request):
    Cart(request).clear()
    messages.success(request, "Cart cleared.")
    return redirect("cart:detail")
