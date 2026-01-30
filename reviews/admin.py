from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "buyer", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("product__title", "buyer__username", "title", "body")
    readonly_fields = ("created_at", "updated_at")
