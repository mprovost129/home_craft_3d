from __future__ import annotations

from .models import Category


def sidebar_categories(request):
    """
    Provides two separate category trees for the global sidebar:
      - model_categories: roots (type=MODEL)
      - file_categories:  roots (type=FILE)

    Children will be accessed via .children in templates.
    """
    model_categories = (
        Category.objects.filter(type=Category.CategoryType.MODEL, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("sort_order", "name")
    )
    file_categories = (
        Category.objects.filter(type=Category.CategoryType.FILE, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("sort_order", "name")
    )
    return {
        "sidebar_model_categories": model_categories,
        "sidebar_file_categories": file_categories,
    }
