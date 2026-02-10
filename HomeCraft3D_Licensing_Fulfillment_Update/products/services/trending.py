# products/services/trending.py
from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from orders.models import Order
from products.models import Product, ProductEngagementEvent


TRENDING_WINDOW_DAYS_DEFAULT = 30
TRENDING_BADGE_TOP_N_DEFAULT = 12

# Cache trending badge membership (IDs) for lightweight per-page badges.
TRENDING_BADGE_CACHE_SECONDS = 60 * 15


def annotate_trending(qs, *, since_days: int = TRENDING_WINDOW_DAYS_DEFAULT):
    """Annotate a Product queryset with a numeric trending_score.

    This function is intentionally self-contained (adds any required annotations)
    so call sites don't have to ensure avg_rating/review_count exist first.
    """
    since = timezone.now() - timedelta(days=since_days)

    avg_rating = Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField())

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

    recent_clicks = Count(
        "engagement_events",
        filter=Q(
            engagement_events__event_type=ProductEngagementEvent.EventType.CLICK,
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
        avg_rating=avg_rating,
        recent_purchases=Coalesce(recent_purchases, Value(0)),
        recent_reviews=Coalesce(recent_reviews, Value(0)),
        recent_views=Coalesce(recent_views, Value(0)),
        recent_clicks=Coalesce(recent_clicks, Value(0)),
        recent_add_to_cart=Coalesce(recent_add_to_cart, Value(0)),
    )

    qs = qs.annotate(
        trending_score=(
            Coalesce(F("recent_purchases"), Value(0)) * Value(6.0)
            + Coalesce(F("recent_add_to_cart"), Value(0)) * Value(3.0)
            + Coalesce(F("recent_clicks"), Value(0)) * Value(1.25)
            + Coalesce(F("recent_reviews"), Value(0)) * Value(2.0)
            + Coalesce(F("recent_views"), Value(0)) * Value(0.25)
            + Coalesce(F("avg_rating"), Value(0.0)) * Value(1.0)
        )
    )

    return qs


def get_trending_badge_ids(
    *,
    since_days: int = TRENDING_WINDOW_DAYS_DEFAULT,
    top_n: int = TRENDING_BADGE_TOP_N_DEFAULT,
) -> set[int]:
    """Return the computed 'Trending' badge membership IDs.

    Rule (locked): Trending badge appears for either:
      - manual Product.is_trending=True
      - OR computed Top N by trending_score (score > 0)

    This function returns only the computed IDs (manual is handled separately).
    """
    try:
        since_days_i = int(since_days)
    except Exception:
        since_days_i = TRENDING_WINDOW_DAYS_DEFAULT

    try:
        top_n_i = int(top_n)
    except Exception:
        top_n_i = TRENDING_BADGE_TOP_N_DEFAULT

    key = f"trending_badge_ids_v1:{since_days_i}:{top_n_i}"
    cached = cache.get(key)
    if isinstance(cached, (set, list, tuple)):
        return set(int(x) for x in cached)

    qs = Product.objects.filter(is_active=True)
    qs = annotate_trending(qs, since_days=since_days_i)
    ids = list(qs.filter(trending_score__gt=0).order_by("-trending_score", "-created_at").values_list("id", flat=True)[:top_n_i])

    result = set(int(x) for x in ids)
    cache.set(key, list(result), TRENDING_BADGE_CACHE_SECONDS)
    return result
