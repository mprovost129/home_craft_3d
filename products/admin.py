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
        "kind",
        "seller",
        "category",
        "is_active",
        "is_featured",
        "is_trending",
        "created_at",
    )
    list_filter = ("kind", "is_active", "is_featured", "is_trending", "category")
    search_fields = ("title", "slug", "seller__username", "short_description", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductImageInline, DigitalAssetInline]


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
    list_display = ("id", "product", "original_filename", "created_at")
    search_fields = ("product__title", "original_filename")


@admin.register(ProductEngagementEvent)
class ProductEngagementEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "product", "created_at")
    list_filter = ("event_type",)
    search_fields = ("product__title", "product__seller__username")
    date_hierarchy = "created_at"
