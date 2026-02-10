# products/admin.py
from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from catalog.models import Category

from .models import (
    Product,
    ProductImage,
    ProductDigital,
    ProductPhysical,
    DigitalAsset,
    ProductEngagementEvent,
    ProductDownloadEvent,
    FilamentRecommendation,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class DigitalAssetInline(admin.TabularInline):
    model = DigitalAsset
    extra = 0


class FilamentRecommendationInline(admin.TabularInline):
    model = FilamentRecommendation
    extra = 0
    fields = ("sort_order", "is_active", "material", "brand", "url", "notes")
    ordering = ("sort_order", "material", "id")
    show_change_link = True


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
        "subcategory",
        "is_active",
        "is_featured",
        "is_trending",
        "max_purchases_per_buyer",
        "created_at",
    )
    list_filter = ("kind", "is_active", "is_featured", "is_trending", "category", "slug_is_manual")
    search_fields = ("title", "slug", "seller__username", "short_description", "description")
    inlines = [ProductImageInline, DigitalAssetInline, FilamentRecommendationInline]

    # IMPORTANT: remove prepopulated_fields so it doesn't fight our model policy
    prepopulated_fields = {}

    class Media:
        # Loaded only in Django admin for this ModelAdmin.
        js = ("products/admin/product_category_subcategory.js",)

    # -------------------------
    # Dependent dropdown support
    # -------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "subcategories-for-category/",
                self.admin_site.admin_view(self.subcategories_for_category),
                name="products_product_subcategories_for_category",
            ),
        ]
        return custom + urls

    def subcategories_for_category(self, request):
        """
        Admin-only JSON endpoint.
        Returns the child categories (subcategories) for a given parent category.
        """
        raw_id = (request.GET.get("category_id") or "").strip()
        try:
            category_id = int(raw_id)
        except Exception:
            return JsonResponse({"results": []})

        parent = Category.objects.filter(pk=category_id).only("id", "type").first()
        if not parent:
            return JsonResponse({"results": []})

        qs = (
            Category.objects.filter(parent_id=parent.id, is_active=True, type=parent.type)
            .only("id", "name")
            .order_by("sort_order", "name")
        )

        results = [{"id": c.id, "text": c.name} for c in qs]
        return JsonResponse({"results": results})

    # -------------------------
    # Better initial queryset
    # -------------------------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Server-side filtering so initial render isn't a huge list.

        - On add page: keep subcategory empty until category selected.
        - On change page: restrict subcategory to children of the object's category.
        - If ?category=<id> is present (rare), also respects that.
        """
        if db_field.name == "subcategory":
            # Default: no subcategories until we know category
            kwargs["queryset"] = Category.objects.none()

            # If editing an existing object, we can restrict based on its category
            obj_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            if obj_id:
                try:
                    obj = Product.objects.select_related("category").only("id", "category_id").get(pk=obj_id)
                    if obj.category_id:
                        kwargs["queryset"] = Category.objects.filter(
                            parent_id=obj.category_id,
                            is_active=True,
                        ).order_by("sort_order", "name")
                except Exception:
                    pass
            else:
                # Add view: keep queryset none here intentionally.
                raw = (request.GET.get("category") or "").strip()
                try:
                    cat_id = int(raw)
                except Exception:
                    cat_id = None
                if cat_id:
                    kwargs["queryset"] = Category.objects.filter(
                        parent_id=cat_id,
                        is_active=True,
                    ).order_by("sort_order", "name")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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


@admin.register(ProductDownloadEvent)
class ProductDownloadEventAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "user", "session_key", "created_at")
    list_filter = ()
    search_fields = ("product__title", "product__seller__username", "user__username", "session_key")
    date_hierarchy = "created_at"


@admin.register(FilamentRecommendation)
class FilamentRecommendationAdmin(admin.ModelAdmin):
    list_display = ("product", "material", "brand", "is_active", "sort_order", "created_at")
    list_filter = ("material", "is_active")
    search_fields = ("product__title", "brand", "url")
    ordering = ("product", "sort_order", "material", "id")
