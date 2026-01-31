from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from orders.models import Order
from payments.models import SellerStripeAccount
from products.permissions import is_owner_user
from .models import Product, ProductEngagementEvent


MIN_REVIEWS_TOP_RATED = 3
TRENDING_WINDOW_DAYS = 30

VIEW_THROTTLE_MINUTES = 10
CLICK_THROTTLE_MINUTES = 5

TRENDING_BADGE_TOP_N = 12


def _base_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category", "seller")
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


def _apply_trending_badge_flag(products: list[Product], *, computed_ids: set[int] | None = None) -> None:
    computed_ids = computed_ids or set()
    for p in products:
        p.trending_badge = bool(getattr(p, "is_trending", False) or (p.id in computed_ids))


def _product_list_common(request: HttpRequest, *, kind: str | None, page_title: str) -> HttpResponse:
    qs = _base_qs()

    if kind in (Product.Kind.MODEL, Product.Kind.FILE):
        qs = qs.filter(kind=kind)

    if not kind:
        kind_filter = (request.GET.get("kind") or "").strip().upper()
        if kind_filter in (Product.Kind.MODEL, Product.Kind.FILE):
            qs = qs.filter(kind=kind_filter)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    sort = (request.GET.get("sort") or "new").strip().lower()
    qs = _annotate_rating(qs)

    trending_fallback = False
    top_fallback = False
    computed_ids: set[int] = set()

    if sort == "trending":
        qs = _annotate_trending(qs, since_days=TRENDING_WINDOW_DAYS)
        qs = qs.order_by("-trending_score", "-avg_rating", "-created_at")
        top_rows = list(qs.filter(trending_score__gt=0).values_list("id", flat=True)[:TRENDING_BADGE_TOP_N])
        computed_ids = set(top_rows)

    elif sort == "top":
        filtered = qs.filter(review_count__gte=MIN_REVIEWS_TOP_RATED).order_by("-avg_rating", "-review_count", "-created_at")
        first = list(filtered.values_list("id", flat=True)[:1])
        if first:
            qs = filtered
            top_fallback = False
        else:
            qs = qs.order_by("-avg_rating", "-review_count", "-created_at")
            top_fallback = True
    else:
        qs = qs.order_by("-created_at")

    products = list(qs)

    if sort == "trending":
        any_signal = any(getattr(p, "trending_score", 0) > 0 for p in products)
        trending_fallback = not any_signal

    _apply_trending_badge_flag(products, computed_ids=computed_ids)

    return render(
        request,
        "products/product_list.html",
        {
            "products": products,
            "q": q,
            "kind": (kind or (request.GET.get("kind") or "")).strip().upper(),
            "page_title": page_title,
            "sort": sort,
            "min_reviews_top_rated": MIN_REVIEWS_TOP_RATED,
            "trending_fallback": trending_fallback,
            "top_fallback": top_fallback,
        },
    )


def product_list(request: HttpRequest) -> HttpResponse:
    return _product_list_common(request, kind=None, page_title="Browse Products")


def models_list(request: HttpRequest) -> HttpResponse:
    return _product_list_common(request, kind=Product.Kind.MODEL, page_title="Browse 3D Models")


def files_list(request: HttpRequest) -> HttpResponse:
    return _product_list_common(request, kind=Product.Kind.FILE, page_title="Browse 3D Files")


def _log_event_throttled(request: HttpRequest, *, product: Product, event_type: str, minutes: int) -> None:
    try:
        key = f"hc3_event_{event_type.lower()}_{product.id}"
        now = timezone.now()
        last_iso = request.session.get(key)
        if last_iso:
            try:
                last_dt = timezone.datetime.fromisoformat(last_iso)
                if timezone.is_naive(last_dt):
                    last_dt = timezone.make_aware(last_dt, timezone.get_current_timezone())
                if now - last_dt < timedelta(minutes=minutes):
                    return
            except Exception:
                pass

        ProductEngagementEvent.objects.create(product=product, event_type=event_type)
        request.session[key] = now.isoformat()
    except Exception:
        return


def product_go(request: HttpRequest, pk: int, slug: str):
    product = get_object_or_404(
        Product.objects.filter(is_active=True).select_related("category", "seller"),
        pk=pk,
        slug=slug,
    )
    _log_event_throttled(
        request,
        product=product,
        event_type=ProductEngagementEvent.EventType.CLICK,
        minutes=CLICK_THROTTLE_MINUTES,
    )
    return redirect("products:detail", pk=product.pk, slug=product.slug)


def _seller_is_ready_to_sell(product: Product) -> bool:
    """
    Matches your SellerStripeAccount fields:
      ready = charges_enabled AND payouts_enabled AND details_submitted
    Owner bypass allowed.
    """
    try:
        if product.seller_id and SellerStripeAccount.objects.filter(
            user_id=product.seller_id,
            charges_enabled=True,
            payouts_enabled=True,
            details_submitted=True,
        ).exists():
            return True
        return bool(product.seller and is_owner_user(product.seller))
    except Exception:
        return False


def product_detail(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    product = get_object_or_404(
        Product.objects.filter(is_active=True)
        .select_related("category", "seller")
        .prefetch_related("images"),
        pk=pk,
        slug=slug,
    )

    _log_event_throttled(
        request,
        product=product,
        event_type=ProductEngagementEvent.EventType.VIEW,
        minutes=VIEW_THROTTLE_MINUTES,
    )

    can_buy = _seller_is_ready_to_sell(product)

    from reviews.models import Review  # local import avoids hard dependency at import-time

    review_qs = Review.objects.filter(product=product).select_related("buyer").order_by("-created_at")
    summary = review_qs.aggregate(avg=Avg("rating"), count=Count("id"))
    avg_rating = summary.get("avg") or 0
    review_count = summary.get("count") or 0
    recent_reviews = list(review_qs[:5])

    more_like_this = (
        _base_qs()
        .filter(kind=product.kind)
        .exclude(pk=product.pk)
        .filter(is_active=True)
    )

    same_cat = more_like_this.filter(category=product.category)
    if same_cat.exists():
        more_like_this = same_cat

    more_like_this = _annotate_rating(more_like_this).order_by("-created_at")[:8]
    more_like_this_list = list(more_like_this)

    _apply_trending_badge_flag(more_like_this_list, computed_ids=set())

    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "more_like_this": more_like_this_list,
            "avg_rating": avg_rating,
            "review_count": review_count,
            "recent_reviews": recent_reviews,
            "can_buy": can_buy,
        },
    )
