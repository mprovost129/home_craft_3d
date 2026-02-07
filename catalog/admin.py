from __future__ import annotations

from django import forms
from django.contrib import admin

from .models import Category, RootCategory, SubCategory


# -----------------------------
# Forms
# -----------------------------

class RootCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = RootCategory
        fields = "__all__"

    def clean_parent(self):
        # Root categories must never have a parent
        return None


class SubCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Limit selectable parents to ROOT categories
        qs = Category.objects.filter(parent__isnull=True)

        # If type is known, filter parents by that type too (MODEL vs FILE)
        chosen_type = None
        if self.data.get("type"):
            chosen_type = self.data.get("type")
        elif getattr(self.instance, "type", None):
            chosen_type = self.instance.type

        if chosen_type:
            qs = qs.filter(type=chosen_type)

        # Explicitly set parent as a ModelChoiceField to support queryset assignment
        self.fields["parent"] = forms.ModelChoiceField(
            queryset=qs.order_by("type", "sort_order", "name"),
            label="Category",
            required=True
        )

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent is None:
            raise forms.ValidationError("A Subcategory must belong to a Category.")

        if parent.parent_id is not None:
            raise forms.ValidationError("Subcategories can only be one level deep (pick a root Category).")

        chosen_type = self.cleaned_data.get("type")
        if chosen_type and parent.type != chosen_type:
            raise forms.ValidationError("Subcategory type must match the selected Category type.")

        return parent


# -----------------------------
# Base Category admin (needed for autocomplete)
# Hidden from admin index/menu
# -----------------------------

@admin.register(Category)
class CategoryHiddenAdmin(admin.ModelAdmin):
    search_fields = ("name", "slug", "description")
    list_filter = ("type", "is_active")
    ordering = ("type", "sort_order", "name")

    def has_module_permission(self, request):
        # Hide "Categories" (base model) from the sidebar/index
        return False


# -----------------------------
# Split UX: Categories vs Subcategories
# -----------------------------

@admin.register(RootCategory)
class RootCategoryAdmin(admin.ModelAdmin):
    form = RootCategoryAdminForm

    list_display = ("name", "type", "is_active", "sort_order", "updated_at")
    list_filter = ("type", "is_active")
    search_fields = ("name", "slug", "description")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        ("Core", {"fields": ("type", "name", "slug", "description")}),
        ("Display", {"fields": ("is_active", "sort_order")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(parent__isnull=True)


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    form = SubCategoryAdminForm

    list_display = ("name", "type", "parent", "is_active", "sort_order", "updated_at")
    list_filter = ("type", "is_active")
    search_fields = ("name", "slug", "description", "parent__name")
    list_editable = ("is_active", "sort_order")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        ("Core", {"fields": ("type", "name", "slug", "parent", "description")}),
        ("Display", {"fields": ("is_active", "sort_order")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(parent__isnull=False)
