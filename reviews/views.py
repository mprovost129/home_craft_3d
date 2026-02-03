from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ReviewForm, SellerReviewForm
from .models import Review, SellerReview
from .services import get_rateable_seller_order_or_403, get_reviewable_order_item_or_403


def product_reviews(request, product_id: int):
    qs = (
        Review.objects.select_related("buyer")
        .filter(product_id=product_id)
        .order_by("-created_at")
    )

    from django.db.models import Avg, Count

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


@require_http_methods(["GET", "POST"])
def seller_review_create(request, order_id: int, seller_id: int):
    """Create a seller rating for a seller within a specific PAID order."""
    try:
        order = get_rateable_seller_order_or_403(user=request.user, order_id=order_id, seller_id=seller_id)
    except PermissionDenied:
        raise Http404("Not found")

    # Prevent duplicates per order
    existing = SellerReview.objects.filter(order_id=order.id, seller_id=seller_id, buyer_id=request.user.id).first()
    if existing:
        messages.info(request, "You already rated this seller for this order.")
        return redirect("orders:detail", order_id=order.id)

    if request.method == "POST":
        form = SellerReviewForm(request.POST)
        if form.is_valid():
            sr: SellerReview = form.save(commit=False)
            sr.order = order
            sr.seller_id = seller_id
            sr.buyer = request.user
            sr.save()
            messages.success(request, "Thanks — your seller rating was posted.")
            return redirect("orders:detail", order_id=order.id)
    else:
        form = SellerReviewForm()

    return render(
        request,
        "reviews/seller_review_form.html",
        {"form": form, "order": order, "seller_id": seller_id},
    )