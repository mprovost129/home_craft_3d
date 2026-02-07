# products/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import (
    Product,
    ProductImage,
    ProductDigital,
    ProductPhysical,
    DigitalAsset,
    ProductEngagementEvent,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class DigitalAssetInline(admin.TabularInline):
    model = DigitalAsset
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "slug",
        "slug_is_manual",
        "kind",
        "seller",
        "category",
        "is_active",
        "is_featured",
        "is_trending",
        "max_purchases_per_buyer",
        "created_at",
    )
    list_filter = ("kind", "is_active", "is_featured", "is_trending", "category", "slug_is_manual")
    search_fields = ("title", "slug", "seller__username", "short_description", "description")
    inlines = [ProductImageInline, DigitalAssetInline]

    # IMPORTANT: remove prepopulated_fields so it doesn't fight our model policy
    prepopulated_fields = {}

    def save_model(self, request, obj, form, change):
        """
        Admin slug policy:
        - If user typed slug -> mark manual
        - If blank -> auto (model generates)
        """
        try:
            raw_slug = (request.POST.get("slug") or "").strip()
            if raw_slug:
                obj.slug_is_manual = True
                obj.slug = raw_slug
            else:
                obj.slug_is_manual = False
                obj.slug = ""
        except Exception:
            pass

        super().save_model(request, obj, form, change)


@admin.register(ProductDigital)
class ProductDigitalAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "file_count")


@admin.register(ProductPhysical)
class ProductPhysicalAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "material", "color")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "is_primary", "sort_order", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__title",)


@admin.register(DigitalAsset)
class DigitalAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "original_filename", "file_type", "created_at")
    list_filter = ("file_type",)
    search_fields = ("product__title", "original_filename")


@admin.register(ProductEngagementEvent)
class ProductEngagementEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "product", "created_at")
    list_filter = ("event_type",)
    search_fields = ("product__title", "product__seller__username")
    date_hierarchy = "created_at"
