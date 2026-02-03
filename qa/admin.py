from django.contrib import admin

from .models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread


@admin.register(ProductQuestionThread)
class ProductQuestionThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "buyer", "created_at", "updated_at", "deleted_at")
    search_fields = ("product__title", "buyer__username", "subject")
    list_filter = ("created_at", "deleted_at")
    raw_id_fields = ("product", "buyer")


@admin.register(ProductQuestionMessage)
class ProductQuestionMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "author", "created_at", "deleted_at")
    search_fields = ("thread__product__title", "author__username", "body")
    list_filter = ("created_at", "deleted_at")
    raw_id_fields = ("thread", "author", "deleted_by")


@admin.register(ProductQuestionReport)
class ProductQuestionReportAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "reason", "message", "reporter", "created_at")
    search_fields = ("message__body", "reporter__username", "details")
    list_filter = ("status", "reason", "created_at")
    raw_id_fields = ("message", "reporter", "resolved_by")
