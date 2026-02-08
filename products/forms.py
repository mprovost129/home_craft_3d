# products/forms.py
from __future__ import annotations

from pathlib import Path
from typing import List

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils.text import slugify

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
            "category": forms.Select(attrs={"class": "form-select"}),
            "subcategory": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "is_free": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "slug": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Leave blank for automatic slug",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Slug is optional: auto-generate unless seller intentionally edits it.
        self.fields["slug"].required = False

        # Filter category queryset by selected kind (MODEL or FILE)
        kind = None
        # 1. POST data (form submission)
        if self.data.get("kind"):
            kind = self.data.get("kind").strip().upper()
        # 2. Instance (edit mode)
        elif self.instance and getattr(self.instance, "kind", None):
            kind = str(self.instance.kind).strip().upper()
        # 3. Default: show all root categories
        if kind == Product.Kind.MODEL:
            self.fields["category"].queryset = Category.objects.filter(parent__isnull=True, is_active=True, type=Category.CategoryType.MODEL).order_by("sort_order", "name")
        elif kind == Product.Kind.FILE:
            self.fields["category"].queryset = Category.objects.filter(parent__isnull=True, is_active=True, type=Category.CategoryType.FILE).order_by("sort_order", "name")
        else:
            self.fields["category"].queryset = Category.objects.filter(parent__isnull=True, is_active=True).order_by("type", "sort_order", "name")

        # Subcategory dropdown: default empty; JS will populate.
        self.fields["subcategory"].queryset = Category.objects.none()
        self.fields["subcategory"].required = False

        # Optional: expose endpoint attr for alternative template/JS patterns
        try:
            self.fields["subcategory"].widget.attrs["data-subcategory-endpoint"] = reverse_lazy(
                "products:seller_subcategories_for_category"
            )
        except Exception:
            pass

        # Determine which category controls the subcategory queryset (edit or postback)
        initial_cat = None

        # Edit view: instance.category
        try:
            if self.instance and self.instance.pk and self.instance.category_id:
                initial_cat = self.instance.category
        except Exception:
            initial_cat = None

        # Postback: use posted category id
        posted_cat_id = (self.data.get("category") or "").strip()
        if posted_cat_id:
            try:
                initial_cat = Category.objects.filter(pk=int(posted_cat_id), parent__isnull=True).first()
            except Exception:
                pass

        # If we have a category, show only its children
        if initial_cat:
            self.fields["subcategory"].queryset = (
                Category.objects.filter(parent=initial_cat, is_active=True).order_by("sort_order", "name")
            )

    def clean_slug(self) -> str:
        """
        Slug policy:
        - Default is AUTO (slug_is_manual=False) when the seller does not touch the slug field.
        - If seller edits slug and provides a value -> MANUAL (slug_is_manual=True), normalized via slugify.
        - If seller edits slug and clears it -> AUTO again (slug_is_manual=False) and blank slug forces regen.
        """
        raw = (self.cleaned_data.get("slug") or "").strip()

        # Only treat as "manual" if the user actually changed the slug field.
        if "slug" in getattr(self, "changed_data", []):
            if raw:
                self.instance.slug_is_manual = True
                return slugify(raw)
            # cleared intentionally -> back to auto
            self.instance.slug_is_manual = False
            return ""

        # Not changed: keep whatever the model/form already has (usually the current slug),
        # and DO NOT flip slug_is_manual.
        return raw

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
        Keep slug behavior consistent with clean_slug():

        - If slug field was changed:
          - non-empty => manual True (already set in clean_slug)
          - empty => manual False (already set in clean_slug) and slug blank forces regen

        - If slug field was NOT changed:
          - do NOT force slug_is_manual=True just because slug exists
        """
        obj: Product = super().save(commit=False)

        if "slug" in getattr(self, "changed_data", []):
            # clean_slug already set slug_is_manual and normalized slug;
            # ensure blank stays blank so model regenerates.
            if not (obj.slug or "").strip():
                obj.slug = ""
                obj.slug_is_manual = False

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
