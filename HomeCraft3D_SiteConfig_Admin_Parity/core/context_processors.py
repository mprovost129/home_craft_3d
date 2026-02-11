# core/context_processors.py

from __future__ import annotations

from typing import Any, Iterable

from django.conf import settings

from payments.models import SellerStripeAccount
from products.permissions import is_owner_user, is_seller_user
from .config import get_site_config


def sidebar_flags(request) -> dict[str, Any]:
    """
    Global sidebar flags used by templates/partials/sidebar_dashboard.html.

    Keeps dashboards templates stable (no need to remember passing these in every view).
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "user_is_owner": False,
            "user_is_seller": False,
            "seller_stripe_ready": None,
        }

    owner = bool(is_owner_user(user))
    seller = bool(is_seller_user(user))

    # Only compute readiness if they're a seller (or owner who can see seller areas).
    # Owner may not have a SellerStripeAccount, so keep it None in that case.
    stripe_ready = None
    if seller:
        acct = (
            SellerStripeAccount.objects.filter(user=user)
            .only(
                "stripe_account_id",
                "details_submitted",
                "charges_enabled",
                "payouts_enabled",
            )
            .first()
        )
        stripe_ready = bool(acct.is_ready) if acct else False

    return {
        "user_is_owner": owner,
        "user_is_seller": seller,
        "seller_stripe_ready": stripe_ready,
    }


def site_config(request) -> dict[str, Any]:
    """
    Provides the singleton SiteConfig to templates.
    Used for footer social links and other global settings.
    """
    return {
        "site_config": get_site_config(),
    }


def analytics(request) -> dict[str, Any]:
    return {
        "ga_measurement_id": (getattr(settings, "GA_MEASUREMENT_ID", "") or "").strip(),
        "recaptcha_site_key": (getattr(settings, "RECAPTCHA_V3_SITE_KEY", "") or "").strip(),
    }


def store_sidebar(request) -> dict[str, Any]:
    """
    Store sidebar data for templates/partials/sidebar_store.html.

    Key rule:
      - Category.type stored values are exactly: "MODEL" and "FILE"
      - Sidebar MUST split by type, otherwise you'll see duplicates under the wrong section
        (e.g. "Games & Toys" exists once for MODEL and once for FILE by design).

    We return only top-level categories and prefetch children to keep template rendering fast.
    """
    # Import inside function so core app doesn't hard-couple at import-time during startup.
    try:
        from catalog.models import Category  # type: ignore
    except Exception:
        # If catalog isn't installed or migrations not applied yet, don't break templates.
        return {
            "sidebar_model_categories": [],
            "sidebar_file_categories": [],
        }

    # Determine ordering fields safely (some installs may not have sort_order).
    field_names: set[str] = {f.name for f in Category._meta.get_fields() if hasattr(f, "name")}
    order_fields: list[str] = []
    if "sort_order" in field_names:
        order_fields.append("sort_order")
    order_fields.append("name")

    # Determine "top-level" filter safely.
    # Most implementations use a nullable FK like parent = models.ForeignKey(..., null=True, blank=True, related_name="children")
    # If your model uses a different structure, this block prevents crashes and falls back gracefully.
    top_level_filter: dict[str, Any] = {"is_active": True, "type": "MODEL"}
    if "parent" in field_names:
        top_level_filter["parent__isnull"] = True

    model_qs = (
        Category.objects.filter(**top_level_filter)
        .prefetch_related("children")
        .order_by(*order_fields)
    )

    top_level_filter_file = dict(top_level_filter)
    top_level_filter_file["type"] = "FILE"
    file_qs = (
        Category.objects.filter(**top_level_filter_file)
        .prefetch_related("children")
        .order_by(*order_fields)
    )

    return {
        "sidebar_model_categories": list(model_qs),
        "sidebar_file_categories": list(file_qs),
    }
