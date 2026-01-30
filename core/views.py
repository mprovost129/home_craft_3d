from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from orders.models import OrderItem, Order
from payments.models import SellerStripeAccount
from products.models import Product
from products.permissions import is_owner_user
from reviews.models import Review


def _base_home_qs():
    """
    Base queryset for home page buckets.
    Only active listings.
    """
    return (
        Product.objects.filter(is_active=True)
        .select_related("seller", "category")
        .prefetch_related("images")
        .order_by("-created_at")
    )


def _annotate_trending(qs, *, since_days: int = 30):
    """
    Adds these annotations:
      - recent_purchases: count of OrderItems for PAID orders in last N days
      - recent_reviews: count of reviews in last N days
      - avg_rating: average rating (all-time)
      - trending_score: weighted sum of above
    """
    since = timezone.now() - timedelta(days=since_days)

    # Purchases: count order items that belong to PAID orders in the window
    # Note: OrderItem.created_at exists, but using Order.paid_at is more correct for "paid demand".
    recent_purchases = Count(
        "order_items",
        filter=Q(
            order_items__order__status=Order.Status.PAID,
            order_items__order__paid_at__isnull=False,
            order_items__order__paid_at__gte=since,
        ),
        distinct=True,
    )

    # Reviews in window
    recent_reviews = Count(
        "reviews",
        filter=Q(reviews__created_at__gte=since),
        distinct=True,
    )

    # Avg rating all-time (simple + stable)
    avg_rating = Avg("reviews__rating")

    qs = qs.annotate(
        recent_purchases=Coalesce(recent_purchases, Value(0)),
        recent_reviews=Coalesce(recent_reviews, Value(0)),
        avg_rating=Coalesce(avg_rating, Value(0.0), output_field=FloatField()),
    )

    # Weighted score:
    # - purchases drive “trending” the most
    # - reviews add confidence + velocity
    # - avg rating adds quality signal, low weight so it doesn’t dominate
    #
    # You can tune weights later.
    qs = qs.annotate(
        trending_score=(
            Coalesce(qs.query.annotations.get("recent_purchases"), Value(0)) * Value(5.0)
            + Coalesce(qs.query.annotations.get("recent_reviews"), Value(0)) * Value(3.0)
            + Coalesce(qs.query.annotations.get("avg_rating"), Value(0.0)) * Value(1.0)
        )
    )

    return qs


def _apply_can_buy_flag(products: list[Product]) -> None:
    """
    Attach `p.can_buy` boolean to each Product instance for templates.
    Efficient: one query to fetch Stripe-ready sellers.
    """
    if not products:
        return

    seller_ids = {p.seller_id for p in products if p.seller_id}
    ready_seller_ids = set(
        SellerStripeAccount.objects.filter(user_id__in=seller_ids, is_ready=True).values_list("user_id", flat=True)
    )

    for p in products:
        try:
            p.can_buy = bool(p.seller_id in ready_seller_ids or is_owner_user(p.seller))
        except Exception:
            p.can_buy = bool(p.seller_id in ready_seller_ids)


def home(request):
    """
    Public landing page.
    Shows Featured / New / Trending / Misc buckets.
    Trending is computed from recent paid purchases + reviews + avg rating,
    with manual is_trending acting as an override for MVP.
    """
    qs = _base_home_qs()

    # Featured: manual, stable
    featured = list(qs.filter(is_featured=True)[:8])

    # New: most recent active
    new_items = list(qs[:8])

    # Trending:
    # 1) Start with manual is_trending items (override)
    # 2) Fill remaining slots with computed trending_score
    manual_trending = list(qs.filter(is_trending=True)[:8])
    manual_ids = {p.id for p in manual_trending}

    trending_needed = max(0, 8 - len(manual_trending))
    computed_trending = []
    if trending_needed > 0:
        trending_qs = _annotate_trending(qs, since_days=30).exclude(id__in=manual_ids)
        computed_trending = list(trending_qs.order_by("-trending_score", "-created_at")[:trending_needed])

    trending = manual_trending + computed_trending

    # Misc: active items not already shown above
    exclude_ids = {p.id for p in featured} | {p.id for p in new_items} | {p.id for p in trending}
    misc = list(qs.exclude(id__in=exclude_ids)[:8])

    # Add Stripe-ready gating flag for Add-to-cart buttons on home cards
    all_cards = featured + new_items + trending + misc
    _apply_can_buy_flag(all_cards)

    return render(
        request,
        "core/home.html",
        {
            "featured": featured,
            "trending": trending,
            "new_items": new_items,
            "misc": misc,
        },
    )
