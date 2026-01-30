from django.contrib import admin

from .models import Product, ProductImage, ProductDigital, DigitalAsset, ProductPhysical


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class DigitalAssetInline(admin.TabularInline):
    model = DigitalAsset
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "kind",
        "seller",
        "category",
        "is_active",
        "is_featured",
        "is_trending",
        "price",
        "created_at",
    )
    list_filter = ("kind", "is_active", "is_featured", "is_trending", "category")
    search_fields = ("title", "slug", "seller__username")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("seller", "category")
    inlines = [ProductImageInline, DigitalAssetInline]

    fieldsets = (
        ("Ownership", {"fields": ("seller", "kind")}),
        ("Listing", {"fields": ("title", "slug", "short_description", "description", "category")}),
        ("Pricing", {"fields": ("is_free", "price")}),
        ("Visibility", {"fields": ("is_active", "is_featured", "is_trending")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductDigital)
class ProductDigitalAdmin(admin.ModelAdmin):
    list_display = ("product", "file_count")
    autocomplete_fields = ("product",)


@admin.register(ProductPhysical)
class ProductPhysicalAdmin(admin.ModelAdmin):
    list_display = ("product", "material", "color", "width_mm", "height_mm", "depth_mm")
    autocomplete_fields = ("product",)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "is_primary", "sort_order", "id")
    list_filter = ("is_primary",)
    autocomplete_fields = ("product",)


@admin.register(DigitalAsset)
class DigitalAssetAdmin(admin.ModelAdmin):
    list_display = ("product", "original_filename", "id", "created_at")
    autocomplete_fields = ("product",)
