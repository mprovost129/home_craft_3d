from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render

from .models import Order, OrderItem


@login_required
def my_orders_list(request):
    orders = (
        Order.objects.filter(buyer=request.user)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product", "seller").order_by("id"),
            )
        )
        .order_by("-created_at")
    )

    return render(request, "orders/buyer/order_list.html", {"orders": orders})
