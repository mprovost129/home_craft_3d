from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from orders.models import Order
from payments.models import SellerStripeAccount
from products.models import Product, ProductEngagementEvent
from products.permissions import is_owner_user


HOME_BUCKET_SIZE = 8
TRENDING_WINDOW_DAYS = 30


def _base_home_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("seller", "category")
        .prefetch_related("images")
    )


def _annotate_rating(qs):
    return qs.annotate(
        avg_rating=Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Coalesce(Count("reviews", distinct=True), Value(0)),
    )


def _annotate_trending(qs, *, since_days: int = TRENDING_WINDOW_DAYS):
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

    recent_views = Count(
        "engagement_events",
        filter=Q(
            engagement_events__event_type=ProductEngagementEvent.EventType.VIEW,
            engagement_events__created_at__gte=since,
        ),
        distinct=True,
    )
    recent_add_to_cart = Count(
        "engagement_events",
        filter=Q(
            engagement_events__event_type=ProductEngagementEvent.EventType.ADD_TO_CART,
            engagement_events__created_at__gte=since,
        ),
        distinct=True,
    )

    qs = qs.annotate(
        recent_purchases=Coalesce(recent_purchases, Value(0)),
        recent_reviews=Coalesce(recent_reviews, Value(0)),
        recent_views=Coalesce(recent_views, Value(0)),
        recent_add_to_cart=Coalesce(recent_add_to_cart, Value(0)),
    )

    qs = qs.annotate(
        trending_score=(
            Coalesce(F("recent_purchases"), Value(0)) * Value(6.0)
            + Coalesce(F("recent_add_to_cart"), Value(0)) * Value(3.0)
            + Coalesce(F("recent_reviews"), Value(0)) * Value(2.0)
            + Coalesce(F("recent_views"), Value(0)) * Value(0.25)
            + Coalesce(F("avg_rating"), Value(0.0)) * Value(1.0)
        )
    )

    return qs


def _apply_can_buy_flag(products: list[Product]) -> None:
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


def _apply_trending_badge_flag(products: list[Product], *, computed_ids: set[int] | None = None) -> None:
    computed_ids = computed_ids or set()
    for p in products:
        p.trending_badge = bool(getattr(p, "is_trending", False) or (p.id in computed_ids))


def home(request):
    qs = _base_home_qs()
    qs = _annotate_rating(qs)

    featured = list(qs.filter(is_featured=True).order_by("-created_at")[:HOME_BUCKET_SIZE])
    new_items = list(qs.order_by("-created_at")[:HOME_BUCKET_SIZE])

    manual_trending = list(qs.filter(is_trending=True).order_by("-created_at")[:HOME_BUCKET_SIZE])
    manual_ids = {p.id for p in manual_trending}

    trending_needed = max(0, HOME_BUCKET_SIZE - len(manual_trending))
    computed_trending: list[Product] = []
    computed_ids: set[int] = set()

    if trending_needed > 0:
        trending_qs = _annotate_trending(qs, since_days=TRENDING_WINDOW_DAYS).exclude(id__in=manual_ids)
        computed_trending = list(
            trending_qs.order_by("-trending_score", "-avg_rating", "-created_at")[:trending_needed]
        )
        computed_ids = {p.id for p in computed_trending}

    trending = manual_trending + computed_trending

    exclude_ids = {p.id for p in featured} | {p.id for p in new_items} | {p.id for p in trending}
    misc = list(qs.exclude(id__in=exclude_ids).order_by("-created_at")[:HOME_BUCKET_SIZE])

    all_cards = featured + new_items + trending + misc
    _apply_can_buy_flag(all_cards)
    _apply_trending_badge_flag(all_cards, computed_ids=computed_ids)

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
