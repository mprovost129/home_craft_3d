from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import ReviewForm
from .models import Review
from .services import get_reviewable_order_item_or_403


def product_reviews(request, product_id: int):
    """
    Public reviews list for a product.
    """
    qs = (
        Review.objects.select_related("buyer")
        .filter(product_id=product_id)
        .order_by("-created_at")
    )

    summary = qs.aggregate(avg=Avg("rating"), count=Count("id"))
    avg_rating = summary.get("avg") or 0
    review_count = summary.get("count") or 0

    return render(
        request,
        "reviews/product_reviews.html",
        {"reviews": qs, "avg_rating": avg_rating, "review_count": review_count, "product_id": product_id},
    )


@require_http_methods(["GET", "POST"])
def review_create_for_order_item(request, order_item_id: int):
    """
    Create a review for a specific purchased OrderItem.
    """
    try:
        item = get_reviewable_order_item_or_403(user=request.user, order_item_id=order_item_id)
    except PermissionDenied:
        raise Http404("Not found")

    if hasattr(item, "review"):
        messages.info(request, "You already reviewed this item.")
        return redirect(item.product.get_absolute_url())

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review: Review = form.save(commit=False)
            review.product = item.product
            review.order_item = item
            review.buyer = request.user
            review.save()
            messages.success(request, "Thanks — your review was posted.")
            return redirect(item.product.get_absolute_url())
    else:
        form = ReviewForm()

    return render(
        request,
        "reviews/review_form.html",
        {"form": form, "item": item, "product": item.product},
    )
