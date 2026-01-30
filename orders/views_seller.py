from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.permissions import seller_required, is_owner_user
from .forms_seller import MarkShippedForm
from .models import Order, OrderItem


def _seller_item_qs(request):
    qs = OrderItem.objects.select_related("order", "product", "seller")
    if is_owner_user(request.user):
        return qs
    return qs.filter(seller=request.user)


@seller_required
def seller_orders_list(request):
    """
    Shows orders that contain at least one item sold by this seller.
    Owner/admin sees all.
    """
    q = (request.GET.get("q") or "").strip()

    items = _seller_item_qs(request)

    if q:
        # Search by order id, title, buyer username (if exists), or tracking number
        items = items.filter(
            Q(order_id__icontains=q)
            | Q(title__icontains=q)
            | Q(tracking_number__icontains=q)
            | Q(order__buyer__username__icontains=q)
        )

    # We want unique orders. We'll build a list of order ids and fetch orders.
    order_ids = (
        items.values_list("order_id", flat=True)
        .distinct()
        .order_by("-order_id")
    )

    orders = (
        Order.objects.filter(id__in=order_ids)
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )

    # Pre-calc: for each order show seller-only stats
    order_meta = {}
    seller_items = _seller_item_qs(request).select_related("order")
    for oid in order_ids:
        o_items = [i for i in seller_items if i.order_id == oid]
        total = sum([i.line_total for i in o_items], start=o_items[0].line_total.__class__("0.00")) if o_items else 0
        unfulfilled = sum(1 for i in o_items if i.fulfillment_status == OrderItem.FulfillmentStatus.UNFULFILLED and i.kind == "MODEL")
        shipped = sum(1 for i in o_items if i.fulfillment_status == OrderItem.FulfillmentStatus.SHIPPED and i.kind == "MODEL")
        order_meta[int(oid)] = {"total": total, "unfulfilled": unfulfilled, "shipped": shipped}

    return render(
        request,
        "orders/seller/order_list.html",
        {"orders": orders, "q": q, "order_meta": order_meta},
    )


def _can_view_order_for_seller(request, order: Order) -> bool:
    if is_owner_user(request.user):
        return True
    return OrderItem.objects.filter(order=order, seller=request.user).exists()


@seller_required
def seller_order_detail(request, order_id: int):
    order = get_object_or_404(Order.objects.prefetch_related("items", "items__product", "items__seller"), pk=order_id)
    if not _can_view_order_for_seller(request, order):
        raise Http404("Not found")

    # Only show this seller's items unless owner/admin
    if is_owner_user(request.user):
        items = order.items.all()
    else:
        items = order.items.filter(seller=request.user)

    shipped_form = MarkShippedForm()
    return render(
        request,
        "orders/seller/order_detail.html",
        {"order": order, "items": items, "shipped_form": shipped_form},
    )


@seller_required
@require_POST
def seller_mark_item_shipped(request, item_id: int):
    item = get_object_or_404(OrderItem.objects.select_related("order", "seller"), pk=item_id)

    # permission
    if not is_owner_user(request.user) and item.seller_id != request.user.id:
        raise Http404("Not found")

    # Only physical models need "shipped". Digital fulfillment handled by downloads.
    if item.kind != "MODEL":
        messages.info(request, "Digital items do not require shipping.")
        return redirect("orders:seller_order_detail", order_id=item.order_id)

    if item.order.status != Order.Status.PAID:
        messages.error(request, "This order is not paid yet.")
        return redirect("orders:seller_order_detail", order_id=item.order_id)

    form = MarkShippedForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid shipping data.")
        return redirect("orders:seller_order_detail", order_id=item.order_id)

    item.mark_shipped(
        tracking_number=form.cleaned_data.get("tracking_number", ""),
        carrier=form.cleaned_data.get("carrier", ""),
    )
    messages.success(request, "Marked shipped.")
    return redirect("orders:seller_order_detail", order_id=item.order_id)
