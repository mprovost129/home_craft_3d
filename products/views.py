# products/views.py
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import F
from products.models import Product

from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount
from products.permissions import is_owner_user
from .models import Product, ProductEngagementEvent, ALLOWED_ASSET_EXTS, FilamentRecommendation, DigitalAsset
from reviews.models import SellerReview
from dashboards.models import ProductFreeUnlock


MIN_REVIEWS_TOP_RATED = 3
TRENDING_WINDOW_DAYS = 30

VIEW_THROTTLE_MINUTES = 10
CLICK_THROTTLE_MINUTES = 5

TRENDING_BADGE_TOP_N = 12


def _file_type_options() -> list[str]:
    preferred = ["stl", "3mf", "obj", "zip"]
    allowed = [t for t in preferred if t in ALLOWED_ASSET_EXTS] + sorted(
        t for t in ALLOWED_ASSET_EXTS if t not in preferred
    )
    return allowed


def _base_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category", "category__parent", "seller", "digital")
        .prefetch_related("images", "digital_assets", "filament_recommendations")
    )


def _annotate_rating(qs):
    qs = qs.annotate(
        avg_rating=Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Coalesce(Count("reviews", distinct=True), Value(0)),
    )

    # Seller reputation (purchased-only seller reviews)
    qs = qs.annotate(
        seller_avg_rating=Coalesce(
            Avg("seller__seller_reviews_received__rating"),
            Value(0.0),
            output_field=FloatField(),
        ),
        seller_review_count=Coalesce(
            Count("seller__seller_reviews_received", distinct=True),
            Value(0),
        ),
    )

    return qs


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
        p.trending_badge = bool(getattr(p, "is_trending", False) or (p.id in computed_ids))  # type: ignore[attr-defined]


def _seller_can_sell(product: Product) -> bool:
    try:
        if product.seller and is_owner_user(product.seller):
            return True
    except Exception:
        pass

    try:
        acct = getattr(product.seller, "stripe_connect", None)
        if acct is not None:
            return bool(acct.is_ready)
    except Exception:
        pass

    try:
        if not product.seller_id:  # type: ignore[attr-defined]
            return False
        return SellerStripeAccount.objects.filter(
            user_id=product.seller_id,  # type: ignore[attr-defined]
            stripe_account_id__gt="",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        ).exists()
    except Exception:
        return False


def _product_list_common(request: HttpRequest, *, kind: str | None, page_title: str) -> HttpResponse:
    qs = _base_qs()

    if kind in (Product.Kind.MODEL, Product.Kind.FILE):
        qs = qs.filter(kind=kind)

    kind_filter = ""
    if not kind:
        kind_filter = (request.GET.get("kind") or "").strip().upper()
        if kind_filter in (Product.Kind.MODEL, Product.Kind.FILE):
            qs = qs.filter(kind=kind_filter)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    file_type = (request.GET.get("file_type") or "").strip().lower().lstrip(".")
    if file_type:
        qs = qs.filter(
            Q(digital_assets__file_type=file_type)
            | Q(digital_assets__file__iendswith=f".{file_type}")
        ).distinct()

    # Price filter
    price_min = (request.GET.get("price_min") or "").strip()
    price_max = (request.GET.get("price_max") or "").strip()
    if price_min:
        try:
            qs = qs.filter(price__gte=Decimal(price_min))
        except Exception:
            pass
    if price_max:
        try:
            qs = qs.filter(price__lte=Decimal(price_max))
        except Exception:
            pass

    # Complexity filter
    complexity = (request.GET.get("complexity") or "").strip()
    if complexity in dict(Product.ComplexityLevel.choices):
        qs = qs.filter(complexity_level=complexity)

    license_type = (request.GET.get("license_type") or "").strip().lower()
    try:
        from products.models import ProductDigital

        if license_type in dict(ProductDigital.LicenseType.choices):
            qs = qs.filter(digital__license_type=license_type)
    except Exception:
        pass

    instant = (request.GET.get("instant") or "").strip()
    if instant == "1":
        qs = qs.filter(kind=Product.Kind.FILE)

    qs = _annotate_rating(qs)

    rating_min_raw = (request.GET.get("rating_min") or "").strip()
    rating_min = ""
    if rating_min_raw:
        try:
            rating_min_val = float(rating_min_raw)
            if 0 < rating_min_val <= 5:
                qs = qs.filter(avg_rating__gte=rating_min_val)
                rating_min = rating_min_raw
        except Exception:
            rating_min = ""

    sort = (request.GET.get("sort") or "new").strip().lower()
    filters_active = any(
        [
            q,
            file_type,
            price_min,
            price_max,
            complexity,
            license_type,
            (instant == "1"),
            rating_min,
            (sort and sort != "new"),
            (kind_filter if not kind else ""),
        ]
    )

    trending_fallback = False
    top_fallback = False
    computed_ids: set[int] = set()

    if sort == "trending":
        qs = _annotate_trending(qs, since_days=TRENDING_WINDOW_DAYS)
        qs = qs.order_by("-trending_score", "-avg_rating", "-created_at")

        top_rows = list(qs.filter(trending_score__gt=0).values_list("id", flat=True)[:TRENDING_BADGE_TOP_N])
        computed_ids = set(top_rows)

    elif sort == "top":
        filtered = qs.filter(review_count__gte=MIN_REVIEWS_TOP_RATED).order_by(
            "-avg_rating", "-review_count", "-created_at"
        )
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

    for p in products:
        p.can_buy = _seller_can_sell(p)  # type: ignore[attr-defined]

    return render(
        request,
        "products/product_list.html",
        {
            "products": products,
            "q": q,
            "kind": (kind or (request.GET.get("kind") or "")).strip().upper(),
            "page_title": page_title,
            "sort": sort,
            "file_type": file_type,
            "file_type_options": _file_type_options(),
            "price_min": price_min,
            "price_max": price_max,
            "complexity": complexity,
            "complexity_options": Product.ComplexityLevel.choices,
            "license_type": license_type,
            "rating_min": rating_min,
            "instant": instant,
            "min_reviews_top_rated": MIN_REVIEWS_TOP_RATED,
            "trending_fallback": trending_fallback,
            "top_fallback": top_fallback,
            "filters_active": filters_active,
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
        key = f"hc3_event_{event_type.lower()}_{product.id}"  # type: ignore[attr-defined]
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


def product_go(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    base_qs = Product.objects.select_related("category", "seller")
    if request.user.is_authenticated and (
        is_owner_user(request.user) or base_qs.filter(pk=pk, slug=slug, seller=request.user).exists()
    ):
        product = get_object_or_404(base_qs, pk=pk, slug=slug)
    else:
        product = get_object_or_404(base_qs.filter(is_active=True), pk=pk, slug=slug)

    if product.is_active:
        _log_event_throttled(
            request,
            product=product,
            event_type=ProductEngagementEvent.EventType.CLICK,
            minutes=5,
        )

    return redirect("products:detail", pk=product.pk, slug=product.slug)


def product_free_asset_download(request: HttpRequest, pk: int, slug: str, asset_id: int) -> HttpResponse:
    """
    Free-download endpoint:
    - Only for active FILE products that are marked free
    - Does not use cart/checkout/orders
    - Increments DigitalAsset.download_count
    """
    base_qs = (
        Product.objects.select_related("seller", "category")
        .prefetch_related("digital_assets")
    )

    # Allow preview access for owner/seller; otherwise only active
    if request.user.is_authenticated and (
        is_owner_user(request.user) or base_qs.filter(pk=pk, slug=slug, seller=request.user).exists()
    ):
        product = get_object_or_404(base_qs, pk=pk, slug=slug)
    else:
        product = get_object_or_404(base_qs.filter(is_active=True), pk=pk, slug=slug)

    if product.kind != Product.Kind.FILE:
        raise Http404("Not a digital product.")

    # IMPORTANT: enforce free-only behavior, or allow if user has free unlock
    has_free_unlock = False
    if request.user.is_authenticated:
        has_free_unlock = ProductFreeUnlock.objects.filter(product=product, user=request.user).exists()
    if not product.is_free and not has_free_unlock:
        raise Http404("This asset requires purchase.")

    # If draft and not owner/seller, it won't be reachable due to query above.
    asset = get_object_or_404(DigitalAsset.objects.select_related("product"), pk=asset_id, product=product)

    # Increment counter (atomic)
    DigitalAsset.objects.filter(pk=asset.pk).update(download_count=F("download_count") + 1)

    # LOCKED: bundle-level count (Seller Listings)
    Product.objects.filter(pk=product.pk).update(download_count=F("download_count") + 1)

    # Serve file
    try:
        fh = asset.file.open("rb")
    except Exception:
        raise Http404("File not available.")

    filename = (asset.original_filename or "").strip()
    if not filename:
        try:
            filename = Path(getattr(asset.file, "name", "") or "").name or "download"
        except Exception:
            filename = "download"

    resp = FileResponse(fh, as_attachment=True, filename=filename)
    return resp


def _render_product_detail(
    *,
    request: HttpRequest,
    product: Product,
    log_event: bool = True,
) -> HttpResponse:
    if log_event and product.is_active:
        _log_event_throttled(
            request,
            product=product,
            event_type=ProductEngagementEvent.EventType.VIEW,
            minutes=10,
        )

    can_buy = product.is_active and _seller_can_sell(product)
    is_preview = not product.is_active

    from reviews.models import Review, SellerReview

    review_qs = (
        Review.objects.filter(product=product)
        .select_related("buyer", "reply", "reply__seller")
        .order_by("-created_at")
    )
    summary = review_qs.aggregate(avg=Avg("rating"), count=Count("id"))
    avg_rating = summary.get("avg") or 0
    review_count = summary.get("count") or 0
    recent_reviews = list(review_qs[:5])

    seller_qs = SellerReview.objects.filter(seller_id=product.seller_id)  # type: ignore[attr-defined]
    seller_summary = seller_qs.aggregate(avg=Avg("rating"), count=Count("id"))
    seller_avg_rating = seller_summary.get("avg") or 0
    seller_review_count = seller_summary.get("count") or 0

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

    related_same_seller_qs = (
        _base_qs()
        .filter(seller_id=product.seller_id, kind=product.kind)  # type: ignore[attr-defined]
        .exclude(pk=product.pk)
    )
    related_same_category_qs = (
        _base_qs()
        .filter(category=product.category, kind=product.kind)
        .exclude(pk=product.pk)
    )

    related_same_seller = list(_annotate_rating(related_same_seller_qs).order_by("-created_at")[:8])
    related_same_category = list(
        _annotate_rating(related_same_category_qs).order_by("-created_at")[:8]
    )

    for p in related_same_seller + related_same_category:
        p.can_buy = _seller_can_sell(p)  # type: ignore[attr-defined]

    filament_recommendations = list(
        FilamentRecommendation.objects.filter(product=product, is_active=True).order_by("sort_order", "material", "id")
    )

    from qa.models import ProductQuestionThread

    qa_threads = (
        ProductQuestionThread.objects.filter(product=product, deleted_at__isnull=True)
        .select_related("buyer", "product", "product__seller")
        .prefetch_related("messages", "messages__author")
        .order_by("-updated_at", "-created_at")
    )

    qa_threads_list = list(qa_threads[:20])
    qa_thread_count = ProductQuestionThread.objects.filter(product=product, deleted_at__isnull=True).count()

    remaining_limit = get_remaining_product_limit(product, request.user)

    is_favorited = False
    is_wishlisted = False
    if request.user.is_authenticated:
        try:
            from favorites.models import Favorite, WishlistItem

            is_favorited = Favorite.objects.filter(user=request.user, product=product).exists()
            is_wishlisted = WishlistItem.objects.filter(user=request.user, product=product).exists()
        except Exception:
            is_favorited = False
            is_wishlisted = False
    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "more_like_this": more_like_this_list,
            "avg_rating": avg_rating,
            "review_count": review_count,
            "recent_reviews": recent_reviews,
            "seller_avg_rating": seller_avg_rating,
            "seller_review_count": seller_review_count,
            "can_buy": can_buy,
            "is_preview": is_preview,
            "related_same_seller": related_same_seller,
            "related_same_category": related_same_category,
            "filament_recommendations": filament_recommendations,
            "qa_threads": qa_threads_list,
            "qa_thread_count": qa_thread_count,
            "remaining_limit": remaining_limit,
            "is_favorited": is_favorited,
            "is_wishlisted": is_wishlisted,
        },
    )


def product_detail(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    base_qs = (
        Product.objects.select_related("category", "category__parent", "seller", "physical", "digital")
        .prefetch_related("images", "digital_assets", "filament_recommendations")
    )

    if request.user.is_authenticated and (
        is_owner_user(request.user) or base_qs.filter(pk=pk, slug=slug, seller=request.user).exists()
    ):
        product = get_object_or_404(base_qs, pk=pk, slug=slug)
    else:
        product = get_object_or_404(base_qs.filter(is_active=True), pk=pk, slug=slug)

    return _render_product_detail(request=request, product=product, log_event=True)


def seller_shop(request: HttpRequest, seller_id: int) -> HttpResponse:
    from reviews.models import SellerReview

    User = get_user_model()
    seller = get_object_or_404(User, pk=seller_id)

    products = _base_qs().filter(seller=seller)
    products = _annotate_rating(products).order_by("-created_at")
    products_list = list(products)

    for p in products_list:
        p.can_buy = _seller_can_sell(p)  # type: ignore[attr-defined]

    seller_reviews = SellerReview.objects.filter(seller=seller).select_related("buyer").order_by("-created_at")
    seller_review_summary = seller_reviews.aggregate(avg=Avg("rating"), count=Count("id"))
    seller_avg_rating = seller_review_summary.get("avg") or 0
    seller_review_count = seller_review_summary.get("count") or 0

    profile = getattr(seller, "profile", None)

    return render(
        request,
        "products/seller_shop.html",
        {
            "seller": seller,
            "products": products_list,
            "seller_avg_rating": seller_avg_rating,
            "seller_review_count": seller_review_count,
            "recent_reviews": list(seller_reviews[:5]),
            "profile": profile,
        },
    )


def get_remaining_product_limit(product: Product, user) -> int | None:
    limit = getattr(product, "max_purchases_per_buyer", None)
    if not limit:
        return None
    if not user or not user.is_authenticated:
        return limit
    purchased = (
        OrderItem.objects.filter(
            product=product,
            order__buyer=user,
            order__status=Order.Status.PAID,
        ).aggregate(total=models.Sum("quantity"))
        or {}
    )
    already = purchased.get("total") or 0
    remaining = max(0, limit - already)
    return remaining


def top_sellers(request: HttpRequest) -> HttpResponse:
    User = get_user_model()
    sellers = (
        User.objects.filter(profile__is_seller=True)
        .annotate(
            seller_review_count=Count("seller_reviews_received", distinct=True),
            seller_avg_rating=Coalesce(Avg("seller_reviews_received__rating"), Value(0.0)),
            product_count=Count("products", distinct=True),
        )
        .order_by("-seller_review_count", "-seller_avg_rating", "-date_joined")[:24]
    )
    sellers = sellers.select_related("profile")
    return render(
        request,
        "products/top_sellers.html",
        {"top_sellers": sellers},
    )
