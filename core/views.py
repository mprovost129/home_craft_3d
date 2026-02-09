# core/views.py
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from catalog.models import Category
from orders.models import Order
from payments.models import SellerStripeAccount
from products.models import Product, ProductEngagementEvent
from products.permissions import is_owner_user


HOME_BUCKET_SIZE = 8
TRENDING_WINDOW_DAYS = 30

# Cache only the fully-rendered anonymous home HTML
HOME_ANON_CACHE_SECONDS = 60 * 15
HOME_ANON_CACHE_KEY = "home_html_anon_v2"


def _base_home_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("seller", "category")
        .prefetch_related("images")
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


def _seller_can_sell(product: Product) -> bool:
    """Single source of truth for buy-gating on the home page."""
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
        if not product.seller_id:
            return False
        return SellerStripeAccount.objects.filter(
            user_id=product.seller_id,
            stripe_account_id__gt="",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        ).exists()
    except Exception:
        return False


def _apply_can_buy_flag(products: list[Product]) -> None:
    for p in products:
        p.can_buy = _seller_can_sell(p)


def _apply_trending_badge_flag(products: list[Product], *, computed_ids: set[int] | None = None) -> None:
    computed_ids = computed_ids or set()
    for p in products:
        p.trending_badge = bool(getattr(p, "is_trending", False) or (p.id in computed_ids))


def _build_home_context(request):
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
        computed_ids = {p.id for p in computed_trending if getattr(p, "trending_score", 0) > 0}

    trending = manual_trending + computed_trending

    exclude_ids = {p.id for p in featured} | {p.id for p in new_items} | {p.id for p in trending}
    misc = list(qs.exclude(id__in=exclude_ids).order_by("-created_at")[:HOME_BUCKET_SIZE])

    # Recently purchased (by paid order date)
    since = timezone.now() - timedelta(days=30)
    recently_purchased = (
        _base_home_qs()
        .annotate(
            recent_purchase_count=Count(
                "order_items",
                filter=Q(
                    order_items__order__status=Order.Status.PAID,
                    order_items__order__paid_at__gte=since,
                ),
                distinct=True,
            )
        )
        .filter(recent_purchase_count__gt=0)
        .order_by("-recent_purchase_count", "-created_at")[:HOME_BUCKET_SIZE]
    )
    recently_purchased = _annotate_rating(recently_purchased)
    recently_purchased_list = list(recently_purchased)
    _apply_can_buy_flag(recently_purchased_list)

    # Most downloaded (using order counts)
    most_downloaded = (
        _base_home_qs()
        .annotate(
            total_purchase_count=Count(
                "order_items",
                filter=Q(order_items__order__status=Order.Status.PAID),
                distinct=True,
            )
        )
        .filter(total_purchase_count__gt=0, kind=Product.Kind.FILE)
        .order_by("-total_purchase_count", "-created_at")[:HOME_BUCKET_SIZE]
    )
    most_downloaded = _annotate_rating(most_downloaded)
    most_downloaded_list = list(most_downloaded)
    _apply_can_buy_flag(most_downloaded_list)

    all_cards = featured + new_items + trending + misc + recently_purchased_list + most_downloaded_list
    _apply_can_buy_flag(all_cards)
    _apply_trending_badge_flag(all_cards, computed_ids=computed_ids)

    # Advertisement banner (show first currently active)
    from core.models_advert import AdvertisementBanner
    ad_banner = AdvertisementBanner.objects.filter(is_active=True).order_by("-created_at").first()

    user_is_seller = False
    user_is_owner = False
    if request.user.is_authenticated:
        user_is_owner = bool(request.user.is_superuser)
        user_is_seller = bool(hasattr(request.user, "profile") and getattr(request.user.profile, "is_seller", False))

    from core.config import get_site_config
    site_config = get_site_config()

    return {
        "featured": featured,
        "trending": trending,
        "new_items": new_items,
        "misc": misc,
        "recently_purchased_list": recently_purchased_list,
        "most_downloaded_list": most_downloaded_list,
        "ad_banner": ad_banner,
        "user_is_seller": user_is_seller,
        "user_is_owner": user_is_owner,
        "site_config": site_config,
    }


def home(request):
    """
    IMPORTANT:
    Do NOT cache the full page for authenticated users.
    Otherwise an anonymous cached navbar gets served to logged-in users.
    """
    if not request.user.is_authenticated:
        cached_html = cache.get(HOME_ANON_CACHE_KEY)
        if cached_html:
            return HttpResponse(cached_html)

        context = _build_home_context(request)
        response = render(request, "core/home.html", context)
        try:
            cache.set(HOME_ANON_CACHE_KEY, response.content.decode("utf-8"), HOME_ANON_CACHE_SECONDS)
        except Exception:
            pass
        return response

    # Authenticated: always render fresh
    context = _build_home_context(request)
    return render(request, "core/home.html", context)


def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)


def robots_txt(request):
    cache_key = "robots_txt_v1"
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type="text/plain")

    base_url = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        base_url = request.build_absolute_uri("/").rstrip("/")

    content = "\n".join(
        [
            "User-agent: *",
            "Disallow:",
            f"Sitemap: {base_url}/sitemap.xml",
        ]
    )
    cache.set(cache_key, content, getattr(settings, "SITEMAP_CACHE_SECONDS", 3600))
    return HttpResponse(content, content_type="text/plain")


def sitemap_xml(request):
    cache_key = "sitemap_xml_v1"
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type="application/xml")

    base_url = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        base_url = request.build_absolute_uri("/").rstrip("/")

    urls: list[str] = [
        urljoin(base_url + "/", ""),
        urljoin(base_url + "/", "products/"),
        urljoin(base_url + "/", "catalog/"),
    ]

    # Categories
    for cat_id in Category.objects.filter(is_active=True).values_list("id", flat=True):
        urls.append(urljoin(base_url + "/", f"catalog/{cat_id}/"))

    # Products (active only)
    for product_id, slug in Product.objects.filter(is_active=True).values_list("id", "slug"):
        urls.append(urljoin(base_url + "/", f"products/{product_id}/{slug}/"))

    xml_lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    xml_lines.extend([f"  <url><loc>{url}</loc></url>" for url in urls])
    xml_lines.append("</urlset>")

    content = "\n".join(xml_lines)
    cache.set(cache_key, content, getattr(settings, "SITEMAP_CACHE_SECONDS", 3600))
    return HttpResponse(content, content_type="application/xml")


def coming_soon(request):
    feature = request.GET.get("feature", "")
    context = {}
    if feature == "blog":
        context["feature_title"] = "Blog"
        context["feature_desc"] = "Our blog will inspire, inform, and connect the Home Craft 3D community!"
    elif feature == "community":
        context["feature_title"] = "Community Chat Board"
        context["feature_desc"] = "Our chat board will be the go-to place for collaboration, support, and fun challenges."
    else:
        context["feature_title"] = None
        context["feature_desc"] = None
    return render(request, "coming_soon.html", context)


def help_page(request):
    """Static help landing (placeholder; can evolve into full help center)."""
    return render(request, "core/help.html", {})


def faqs_page(request):
    """Static FAQs page (placeholder; can evolve later)."""
    return render(request, "core/faqs.html", {})


def tips_page(request):
    """Static Tips & Tricks page (locked to be static now; blog later)."""
    return render(request, "core/tips.html", {})
