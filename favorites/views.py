from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from products.models import Product

from .models import Favorite, WishlistItem


@login_required
def library(request: HttpRequest) -> HttpResponse:
    """Single page showing Favorites + Wishlist."""
    user = request.user

    favorites_qs = (
        Favorite.objects.filter(user=user)
        .select_related("product", "product__seller", "product__category")
        .prefetch_related("product__images")
        .order_by("-created_at")
    )
    wishlist_qs = (
        WishlistItem.objects.filter(user=user)
        .select_related("product", "product__seller", "product__category")
        .prefetch_related("product__images")
        .order_by("-created_at")
    )

    return render(
        request,
        "favorites/library.html",
        {
            "favorites": list(favorites_qs),
            "wishlist_items": list(wishlist_qs),
            "favorite_count": favorites_qs.count(),
            "wishlist_count": wishlist_qs.count(),
        },
    )


@login_required
def favorite_add(request: HttpRequest, product_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("favorites:library")

    product = get_object_or_404(Product, pk=product_id)
    try:
        Favorite.objects.create(user=request.user, product=product)
        messages.success(request, "Added to favorites.")
    except IntegrityError:
        messages.info(request, "Already in favorites.")

    return redirect(request.POST.get("next") or product.get_absolute_url())


@login_required
def favorite_remove(request: HttpRequest, product_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("favorites:library")

    Favorite.objects.filter(user=request.user, product_id=product_id).delete()
    messages.success(request, "Removed from favorites.")
    return redirect(request.POST.get("next") or "favorites:library")


@login_required
def wishlist_add(request: HttpRequest, product_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("favorites:library")

    product = get_object_or_404(Product, pk=product_id)
    try:
        WishlistItem.objects.create(user=request.user, product=product)
        messages.success(request, "Added to wishlist.")
    except IntegrityError:
        messages.info(request, "Already in wishlist.")

    return redirect(request.POST.get("next") or product.get_absolute_url())


@login_required
def wishlist_remove(request: HttpRequest, product_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("favorites:library")

    WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
    messages.success(request, "Removed from wishlist.")
    return redirect(request.POST.get("next") or "favorites:library")
