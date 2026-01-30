from __future__ import annotations

from django import forms

from catalog.models import Category
from .models import Product, ProductImage, DigitalAsset


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "kind",
            "title",
            "slug",
            "short_description",
            "description",
            "category",
            "is_free",
            "price",
            "is_active",
            "is_featured",
            "is_trending",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # For MVP: show only active categories, ordered nicely
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("type", "parent_id", "sort_order", "name")

        # If kind is already known, narrow category choices to the matching tree
        kind_value = None
        if self.instance and self.instance.pk:
            kind_value = self.instance.kind
        else:
            kind_value = self.data.get("kind") or self.initial.get("kind")

        if kind_value in (Product.Kind.MODEL, Product.Kind.FILE):
            expected_type = Category.CategoryType.MODEL if kind_value == Product.Kind.MODEL else Category.CategoryType.FILE
            self.fields["category"].queryset = self.fields["category"].queryset.filter(type=expected_type)

        # Make slug optional; we auto-generate in save() if empty
        self.fields["slug"].required = False

    def clean(self):
        cleaned = super().clean()

        is_free = cleaned.get("is_free")
        price = cleaned.get("price")

        if is_free:
            cleaned["price"] = 0
        else:
            # allow empty price to error clearly
            if price is None:
                self.add_error("price", "Price is required unless the item is marked free.")
            else:
                try:
                    if price <= 0:
                        self.add_error("price", "Price must be greater than $0.00 unless the item is marked free.")
                except TypeError:
                    self.add_error("price", "Enter a valid price.")

        return cleaned


class ProductImageUploadForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary", "sort_order"]


class DigitalAssetUploadForm(forms.ModelForm):
    class Meta:
        model = DigitalAsset
        fields = ["file", "original_filename"]

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.original_filename and obj.file:
            obj.original_filename = getattr(obj.file, "name", "") or ""
        if commit:
            obj.save()
        return obj
