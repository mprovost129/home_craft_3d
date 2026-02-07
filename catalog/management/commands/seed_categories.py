# catalog/context_processors.py

from __future__ import annotations

from django.core.cache import cache
from django.db.models import Prefetch

from .models import Category
from products.models import ALLOWED_ASSET_EXTS, Product, ProductDigital


def sidebar_categories(request):
    """
    Provides two separate category trees for the global sidebar:
      - sidebar_model_categories: roots (type=MODEL)
      - sidebar_file_categories:  roots (type=FILE)

    Children are prefetched as active-only and ordered alphabetically.
    """
    cache_key = "sidebar_categories_v2"  # bump to invalidate old cached payload
    cached = cache.get(cache_key)
    if cached:
        return cached

    active_children = Prefetch(
        "children",
        queryset=Category.objects.filter(is_active=True).order_by("name"),
    )

    model_categories = (
        Category.objects.filter(type=Category.CategoryType.MODEL, parent__isnull=True, is_active=True)
        .prefetch_related(active_children)
        .order_by("name")
    )

    file_categories = (
        Category.objects.filter(type=Category.CategoryType.FILE, parent__isnull=True, is_active=True)
        .prefetch_related(active_children)
        .order_by("name")
    )

    preferred = ["stl", "3mf", "obj", "zip"]
    allowed = [t for t in preferred if t in ALLOWED_ASSET_EXTS] + sorted(
        t for t in ALLOWED_ASSET_EXTS if t not in preferred
    )

    payload = {
        "sidebar_model_categories": model_categories,
        "sidebar_file_categories": file_categories,
        "sidebar_file_type_options": allowed,
        "sidebar_complexity_options": Product.ComplexityLevel.choices,
        "sidebar_license_type_options": ProductDigital.LicenseType.choices,
    }
    cache.set(cache_key, payload, 3600)
    return payload
