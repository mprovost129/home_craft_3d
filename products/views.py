from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, FloatField, Q, Value, F
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from orders.models import Order
from .models import Product


def _annotate_ratings(qs):
    """
    Adds:
      - avg_rating (float)
      - review_count (int)
    """
    return qs.annotate(
        avg_rating=Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Coalesce(Count("reviews", distinct=True), Value(0)),
    )


def _annotate_trending(qs, *, since_days: int = 30):
    """
    Adds:
      - recent_purchases (int) (paid in last N days)
      - recent_reviews (int)   (created in last N days)
      - avg_rating (float)
      - review_count (int)
      - trending_score (float)
    """
    since = timezone.now() - timedelta(days=since_days)

    recent_purchases = Count(
        "order_items",
        filter=Q(
            order_items__order__status=Order.Status.PAID,
            order_items__order__paid_at__isnull=False,
            order_items__order__paid_at__gte=since,
        ),
        distinct=True,
    )

    recent_reviews = Count(
        "reviews",
        filter=Q(reviews__created_at__gte=since),
        distinct=True,
    )

    qs = qs.annotate(
        recent_purchases=Coalesce(recent_purchases, Value(0)),
        recent_reviews=Coalesce(recent_reviews, Value(0)),
    )

    qs = _annotate_ratings(qs)

    return qs.annotate(
        trending_score=(
            Coalesce(F("recent_purchases"), Value(0)) * Value(5.0)
            + Coalesce(F("recent_reviews"), Value(0)) * Value(3.0)
            + Coalesce(F("avg_rating"), Value(0.0)) * Value(1.0)
        )
    )


def _product_list_common(request, *, kind: str | None, page_title: str):
    qs = (
        Product.objects.filter(is_active=True)
        .select_related("category", "seller")
        .prefetch_related("images")
    )

    q = (request.GET.get("q") or "").strip()

    # kind filter (locked views pass kind, all-products view can pass ?kind=)
    requested_kind = (request.GET.get("kind") or "").strip()
    if kind in (Product.Kind.MODEL, Product.Kind.FILE):
        qs = qs.filter(kind=kind)
        effective_kind = kind
    else:
        if requested_kind in (Product.Kind.MODEL, Product.Kind.FILE):
            qs = qs.filter(kind=requested_kind)
            effective_kind = requested_kind
        else:
            effective_kind = ""

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )

    # Sort controls
    sort = (request.GET.get("sort") or "new").strip()

    sort_choices = [
        ("new", "New"),
        ("trending", "Trending"),
        ("rating", "Top rated"),
        ("price_low", "Price: low → high"),
        ("price_high", "Price: high → low"),
    ]

    # Default annotations for card display stability
    qs = _annotate_ratings(qs)

    trending_window_days = 30

    if sort == "trending":
        qs = _annotate_trending(qs, since_days=trending_window_days).order_by("-trending_score", "-created_at")
    elif sort == "rating":
        qs = qs.order_by("-avg_rating", "-review_count", "-created_at")
    elif sort == "price_low":
        qs = qs.order_by("price", "-created_at")
    elif sort == "price_high":
        qs = qs.order_by("-price", "-created_at")
    else:
        sort = "new"
        qs = qs.order_by("-created_at")

    return render(
        request,
        "products/product_list.html",
        {
            "products": qs,
            "q": q,
            "kind": effective_kind,
            "page_title": page_title,
            "sort": sort,
            "sort_choices": sort_choices,
            "trending_window_days": trending_window_days,
        },
    )


def product_list(request):
    """
    All products (with optional kind filter + sort).
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
