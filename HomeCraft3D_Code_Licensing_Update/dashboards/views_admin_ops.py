from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from orders.models import Order
from payments.service.stripe_reconcile import reconcile_order


@staff_member_required
def admin_reconciliation(request):
    rows = []

    orders = (
        Order.objects
        .prefetch_related("items")
        .order_by("-created_at")[:100]
    )

    for order in orders:
        data = reconcile_order(order)
        rows.append({
            "order": order,
            **data,
        })

    return render(
        request,
        "dashboards/admin_reconciliation.html",
        {"rows": rows},
    )
