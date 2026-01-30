from __future__ import annotations

from django.db.models import Q, Avg, Count
from django.shortcuts import get_object_or_404, render

from .models import Product


def _product_list_common(request, *, kind: str | None, page_title: str):
    qs = (
        Product.objects.filter(is_active=True)
        .select_related("category", "seller")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    q = (request.GET.get("q") or "").strip()

    if kind in (Product.Kind.MODEL, Product.Kind.FILE):
        qs = qs.filter(kind=kind)

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )

    return render(
        request,
        "products/product_list.html",
        {
            "products": qs,
            "q": q,
            "kind": kind or "",
            "page_title": page_title,
        },
    )


def product_list(request):
    """
    All products.
    """
    return _product_list_common(request, kind=None, page_title="Browse Products")


def models_list(request):
    """
    Physical models browse page.
    """
    return _product_list_common(request, kind=Product.Kind.MODEL, page_title="Browse 3D Models")


def files_list(request):
    """
    Digital files browse page.
    """
    return _product_list_common(request, kind=Product.Kind.FILE, page_title="Browse 3D Files")


def product_detail(request, pk: int, slug: str):
    product = get_object_or_404(
        Product.objects.filter(is_active=True)
        .select_related("category", "seller")
        .prefetch_related("images"),
        pk=pk,
        slug=slug,
    )

    # Reviews summary + recent reviews (MVP)
    from reviews.models import Review  # local import avoids hard dependency at import-time

    review_qs = Review.objects.filter(product=product).select_related("buyer").order_by("-created_at")
    summary = review_qs.aggregate(avg=Avg("rating"), count=Count("id"))
    avg_rating = summary.get("avg") or 0
    review_count = summary.get("count") or 0
    recent_reviews = list(review_qs[:5])

    # MVP "More like this": same kind + same category (fallback: same kind)
    more_like_this = (
        Product.objects.filter(is_active=True, kind=product.kind)
        .exclude(pk=product.pk)
        .select_related("category", "seller")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    more_like_this_same_cat = more_like_this.filter(category=product.category)[:8]
    if more_like_this_same_cat:
        more_like_this = more_like_this_same_cat
    else:
        more_like_this = more_like_this[:8]

    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "more_like_this": more_like_this,
            "avg_rating": avg_rating,
            "review_count": review_count,
            "recent_reviews": recent_reviews,
        },
    )
