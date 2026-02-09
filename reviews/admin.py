# reviews/admin.py
from django.contrib import admin

from .models import Review, SellerReview


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "buyer", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("product__title", "buyer__username", "title", "body")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SellerReview)
class SellerReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "buyer", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("seller__username", "buyer__username", "title", "body")
