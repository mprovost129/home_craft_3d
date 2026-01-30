from __future__ import annotations

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from .models import Category
from products.models import Product


def category_list(request):
    """
    Browse categories (top-level)
    """
    model_roots = (
        Category.objects.filter(type=Category.CategoryType.MODEL, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("sort_order", "name")
    )
    file_roots = (
        Category.objects.filter(type=Category.CategoryType.FILE, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("sort_order", "name")
    )

    return render(
        request,
        "catalog/category_list.html",
        {"model_roots": model_roots, "file_roots": file_roots},
    )


def category_detail(request, pk: int):
    """
    Category page: show products for the category (and optionally its descendants).
    MVP behavior:
      - show products in this category + direct children
      - show inactive products? NO (only active)
    """
    category = get_object_or_404(Category.objects.select_related("parent"), pk=pk, is_active=True)

    # Include this category + direct children (MVP)
    child_ids = list(category.children.filter(is_active=True).values_list("id", flat=True))
    category_ids = [category.id] + child_ids

    products_qs = (
        Product.objects.filter(is_active=True, category_id__in=category_ids)
        .select_related("category", "seller")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    # For page sidebar / nav: show children as quick chips
    children = category.children.filter(is_active=True).order_by("sort_order", "name")

    return render(
        request,
        "catalog/category_detail.html",
        {
            "category": category,
            "children": children,
            "products": products_qs,
        },
    )
