# products/forms.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from catalog.models import Category
from .models import Product, ProductImage, DigitalAsset, ProductPhysical, ProductDigital


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


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs["multiple"] = True
        super().__init__(attrs)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "kind",
            "category",
            "subcategory",
            "title",
            "short_description",
            "description",
            "price",
            "is_free",
            "is_active",
            "slug",
        ]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select", "id": "category-select"}),
            "subcategory": forms.Select(attrs={"class": "form-select", "id": "subcategory-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "is_free": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Category dropdown should only show ROOT categories (parent is null)
        self.fields["category"].queryset = (
            Category.objects.filter(parent__isnull=True, is_active=True).order_by("type", "sort_order", "name")
        )

        # Subcategory dropdown: start empty; JS will populate. On edit/postback, we populate if possible.
        self.fields["subcategory"].queryset = Category.objects.none()
        self.fields["subcategory"].required = False

        initial_cat = None
        try:
            if self.instance and self.instance.pk and self.instance.category_id:
                initial_cat = self.instance.category
        except Exception:
            initial_cat = None

        posted_cat_id = (self.data.get("category") or "").strip()
        if posted_cat_id:
            try:
                initial_cat = Category.objects.filter(pk=int(posted_cat_id), parent__isnull=True).first()
            except Exception:
                pass

        if initial_cat:
            self.fields["subcategory"].queryset = (
                Category.objects.filter(parent=initial_cat, is_active=True).order_by("sort_order", "name")
            )

    def clean(self):
        cleaned = super().clean()

        kind = (cleaned.get("kind") or "").strip().upper()
        category: Category | None = cleaned.get("category")
        subcategory: Category | None = cleaned.get("subcategory")

        if category:
            if category.parent_id is not None:
                raise ValidationError({"category": "Category must be a top-level category (not a subcategory)."})

            if kind == Product.Kind.MODEL and category.type != Category.CategoryType.MODEL:
                raise ValidationError({"category": "Model products must use a 3D Models category."})
            if kind == Product.Kind.FILE and category.type != Category.CategoryType.FILE:
                raise ValidationError({"category": "File products must use a 3D Files category."})

        if subcategory:
            if subcategory.parent_id is None:
                raise ValidationError({"subcategory": "Subcategory must be a child of a Category."})

            if category and subcategory.parent_id != category.id:
                raise ValidationError({"subcategory": "Subcategory must belong to the selected Category."})

            if category and subcategory.type != category.type:
                raise ValidationError({"subcategory": "Subcategory type must match the Category type."})

        return cleaned

    def save(self, commit=True):
        """
        Slug policy from the form:
        - If user typed a slug -> mark as manual.
        - If slug is blank -> leave slug_is_manual=False and allow model auto-generation.
        """
        obj: Product = super().save(commit=False)

        raw_slug = (self.cleaned_data.get("slug") or "").strip()
        if raw_slug:
            # user explicitly set slug
            obj.slug_is_manual = True
            obj.slug = raw_slug
        else:
            # auto slug (model will generate/update based on title)
            obj.slug_is_manual = False
            obj.slug = ""

        if commit:
            obj.full_clean()
            obj.save()
            self.save_m2m()

        return obj


class ProductImageUploadForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary", "sort_order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs.setdefault("class", "form-control")
        self.fields["image"].widget.attrs.setdefault("accept", "image/*")
        self.fields["alt_text"].widget.attrs.setdefault("class", "form-control")
        self.fields["is_primary"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["sort_order"].widget.attrs.setdefault("class", "form-control")

    def clean_image(self):
        img = self.cleaned_data.get("image")
        _validate_upload(img, allowed_exts=ALLOWED_IMAGE_EXTS, max_mb=MAX_IMAGE_MB)
        return img


class ProductImageBulkUploadForm(forms.Form):
    images = forms.FileField(
        widget=MultiFileInput(
            attrs={
                "accept": "image/*",
                "class": "form-control",
            }
        ),
        required=True,
        help_text=f"Select one or more images. Supported: {', '.join(sorted(ALLOWED_IMAGE_EXTS))} (up to {MAX_IMAGE_MB}MB each).",
    )

    def clean_images(self):
        files = self.files.getlist("images")
        if not files:
            raise forms.ValidationError("Please select at least one image.")

        for f in files:
            _validate_upload(f, allowed_exts=ALLOWED_IMAGE_EXTS, max_mb=MAX_IMAGE_MB)

        return files


class DigitalAssetUploadForm(forms.ModelForm):
    class Meta:
        model = DigitalAsset
        fields = ["file", "file_type", "original_filename"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        preferred = ["stl", "3mf", "obj", "zip"]
        allowed = [t for t in preferred if t in ALLOWED_ASSET_EXTS] + sorted(
            t for t in ALLOWED_ASSET_EXTS if t not in preferred
        )

        if "file_type" in self.fields:
            self.fields["file_type"].choices = [(t, f".{t}") for t in allowed]
            self.fields["file_type"].required = True

        if "file" in self.fields:
            self.fields["file"].widget.attrs.setdefault("class", "form-control")
        if "file_type" in self.fields:
            self.fields["file_type"].widget.attrs.setdefault("class", "form-select")
        if "original_filename" in self.fields:
            self.fields["original_filename"].widget.attrs.setdefault("class", "form-control")

    def clean_file(self):
        f = self.cleaned_data.get("file")
        _validate_upload(f, allowed_exts=ALLOWED_ASSET_EXTS, max_mb=MAX_ASSET_MB)
        return f

    def clean(self):
        cleaned = super().clean()
        f = cleaned.get("file")
        file_type = (cleaned.get("file_type") or "").lower().lstrip(".")
        if f and file_type:
            name = getattr(f, "name", "") or ""
            ext = Path(name).suffix.lower().lstrip(".")
            if ext and ext != file_type:
                self.add_error("file_type", "Selected file type does not match file extension.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.original_filename and obj.file:
            obj.original_filename = getattr(obj.file, "name", "") or ""
        if commit:
            obj.full_clean()
            obj.save()
        return obj


class ProductPhysicalForm(forms.ModelForm):
    class Meta:
        model = ProductPhysical
        fields = [
            "material",
            "color",
            "num_colors",
            "width_mm",
            "height_mm",
            "depth_mm",
            "weight_grams",
            "support_required",
            "specifications",
        ]
        widgets = {
            "material": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Plastic, Resin, Metal"}),
            "color": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., White, Multi-color"}),
            "num_colors": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Number of colors"}),
            "width_mm": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Width in mm"}),
            "height_mm": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Height in mm"}),
            "depth_mm": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Depth in mm"}),
            "weight_grams": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Weight in grams"}),
            "support_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "specifications": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Additional specs, assembly instructions, etc."}),
        }


class ProductDigitalForm(forms.ModelForm):
    class Meta:
        model = ProductDigital
        fields = [
            "software_requirements",
            "compatible_software",
            "license_type",
            "requirements",
        ]
        widgets = {
            "software_requirements": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Fusion 360, FreeCAD, Blender"}),
            "compatible_software": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Windows, macOS, Linux"}),
            "license_type": forms.Select(attrs={"class": "form-select"}),
            "requirements": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "System requirements, dependencies, additional info"}),
        }
