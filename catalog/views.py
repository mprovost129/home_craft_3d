from __future__ import annotations

from django.shortcuts import get_object_or_404, render

from .models import Category


def category_list(request):
    """
    Simple browse page for categories.
    Later this will evolve into:
      /models/ browse
      /files/ browse
    but for MVP we show both groups.
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
        {
            "model_roots": model_roots,
            "file_roots": file_roots,
        },
    )


def category_detail(request, pk: int):
    """
    Category detail page placeholder.
    Later: show products inside this category.
    """
    category = get_object_or_404(Category, pk=pk, is_active=True)
    return render(request, "catalog/category_detail.html", {"category": category})
