from __future__ import annotations

from django.db.models import QuerySet
from django.shortcuts import render

from payments.models import SellerStripeAccount
from products.models import Product
from products.permissions import is_owner_user


def _base_home_qs() -> QuerySet[Product]:
    """
    Shared queryset for home page buckets.
    """
    return (
        Product.objects.filter(is_active=True)
        .select_related("seller", "category")
        .prefetch_related("images")
        .order_by("-created_at")
    )


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
        # Owner/admin sellers treated as ready (bypass)
        try:
            p.can_buy = bool(p.seller_id in ready_seller_ids or is_owner_user(p.seller))
        except Exception:
            p.can_buy = bool(p.seller_id in ready_seller_ids)


def home(request):
    """
    Public landing page.
    Logged-out users land here.
    Logged-in users still see this unless redirected elsewhere later.
    """
    qs = _base_home_qs()

    featured = list(qs.filter(is_featured=True)[:8])
    trending = list(qs.filter(is_trending=True)[:8])
    new_items = list(qs[:8])

    # "Misc" = active items not already shown above (simple MVP)
    exclude_ids = {p.id for p in featured} | {p.id for p in trending} | {p.id for p in new_items}
    misc = list(qs.exclude(id__in=exclude_ids)[:8])

    # Apply purchase-eligibility flag for UX (backend still enforces)
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
