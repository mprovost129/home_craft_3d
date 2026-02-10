from __future__ import annotations

from django.contrib import admin

from .models import Favorite, WishlistItem


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "product__title")
    raw_id_fields = ("user", "product")
    ordering = ("-created_at",)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "product__title")
    raw_id_fields = ("user", "product")
    ordering = ("-created_at",)
