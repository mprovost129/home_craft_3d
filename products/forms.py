from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings

from catalog.models import Category
from .models import Product, ProductImage, DigitalAsset


def _get_setting_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default) or default)
    except Exception:
        return default


def _get_setting_set(name: str, default: set[str]) -> set[str]:
    raw = getattr(settings, name, None)
    if not raw:
        return default
    if isinstance(raw, (list, tuple, set)):
        return {str(x).lower().lstrip(".") for x in raw if str(x).strip()}
    if isinstance(raw, str):
        return {x.strip().lower().lstrip(".") for x in raw.split(",") if x.strip()}
    return default


DEFAULT_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
DEFAULT_ASSET_EXTS = {"stl", "obj", "3mf", "zip"}

MAX_IMAGE_MB = _get_setting_int("HC3_MAX_IMAGE_MB", 8)
MAX_ASSET_MB = _get_setting_int("HC3_MAX_ASSET_MB", 200)

ALLOWED_IMAGE_EXTS = _get_setting_set("HC3_ALLOWED_IMAGE_EXTS", DEFAULT_IMAGE_EXTS)
ALLOWED_ASSET_EXTS = _get_setting_set("HC3_ALLOWED_ASSET_EXTS", DEFAULT_ASSET_EXTS)


def _validate_upload(file_obj, *, allowed_exts: set[str], max_mb: int) -> None:
    if not file_obj:
        return
    name = getattr(file_obj, "name", "") or ""
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in allowed_exts:
        raise forms.ValidationError(f"Unsupported file type .{ext or '?'}")

    size = getattr(file_obj, "size", None)
    if size is not None:
        limit_bytes = int(max_mb) * 1024 * 1024
        if int(size) > limit_bytes:
            raise forms.ValidationError(f"File too large. Max {max_mb} MB.")


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
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by(
            "type", "parent_id", "sort_order", "name"
        )

        kind_value = None
        if self.instance and self.instance.pk:
            kind_value = self.instance.kind
        else:
            kind_value = self.data.get("kind") or self.initial.get("kind")

        if kind_value in (Product.Kind.MODEL, Product.Kind.FILE):
            expected_type = Category.CategoryType.MODEL if kind_value == Product.Kind.MODEL else Category.CategoryType.FILE
            self.fields["category"].queryset = self.fields["category"].queryset.filter(type=expected_type)

        self.fields["slug"].required = False

    def clean(self):
        cleaned = super().clean()
        is_free = cleaned.get("is_free")
        price = cleaned.get("price")

        if is_free:
            cleaned["price"] = 0
        else:
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

    def clean_image(self):
        img = self.cleaned_data.get("image")
        _validate_upload(img, allowed_exts=ALLOWED_IMAGE_EXTS, max_mb=MAX_IMAGE_MB)
        return img


class DigitalAssetUploadForm(forms.ModelForm):
    class Meta:
        model = DigitalAsset
        fields = ["file", "original_filename"]

    def clean_file(self):
        f = self.cleaned_data.get("file")
        _validate_upload(f, allowed_exts=ALLOWED_ASSET_EXTS, max_mb=MAX_ASSET_MB)
        return f

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.original_filename and obj.file:
            obj.original_filename = getattr(obj.file, "name", "") or ""
        if commit:
            obj.full_clean()
            obj.save()
        return obj
