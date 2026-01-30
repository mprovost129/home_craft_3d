from django.contrib import admin
from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "parent", "is_active", "sort_order", "updated_at")
    list_filter = ("type", "is_active")
    search_fields = ("name", "slug", "description")
    list_editable = ("is_active", "sort_order")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        ("Core", {"fields": ("type", "name", "slug", "parent", "description")}),
        ("Display", {"fields": ("is_active", "sort_order")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")
