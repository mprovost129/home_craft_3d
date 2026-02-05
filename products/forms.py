# products/forms.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

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


class MultiFileInput(forms.ClearableFileInput):
    """
    Correct Django-supported way to enable <input type="file" multiple>.
    Do NOT pass `multiple=True` to the widget; Django will raise ValueError.
    """
    allow_multiple_selected = True


def _category_choices_for_form(qs: Iterable[Category]) -> List[Tuple[str, List[Tuple[int, str]]]]:
    """
    Build optgrouped <select> choices to reduce scrolling:
      - Groups by parent category
      - Shows children under each group
      - If no parent/children, still lists under a sensible group
    Returns a structure Django accepts for Field.choices:
      [("Group label", [(value,label), ...]), ...]
    """
    # Materialize (we use it multiple times)
    cats = list(qs)

    by_parent: dict[int | None, list[Category]] = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)

    # Parents are those with parent_id=None
    parents = by_parent.get(None, [])
    # Sort parents by sort_order, name (qs should already be ordered, but keep stable)
    parents = sorted(parents, key=lambda x: (getattr(x, "sort_order", 0), x.name.lower(), x.id))

    groups: List[Tuple[str, List[Tuple[int, str]]]] = []

    used_ids: set[int] = set()

    # Build groups for each parent
    for parent in parents:
        children = by_parent.get(parent.id, [])
        children = sorted(children, key=lambda x: (getattr(x, "sort_order", 0), x.name.lower(), x.id))

        # Include the parent itself as a selectable option too (if your data allows products on parents)
        # If you *never* allow selecting parents, remove this block.
        group_items: List[Tuple[int, str]] = []
        group_items.append((parent.id, f"{parent.name}"))

        used_ids.add(parent.id)

        for ch in children:
            group_items.append((ch.id, f"— {ch.name}"))
            used_ids.add(ch.id)

        groups.append((parent.name, group_items))

    # Any orphans (categories whose parent isn't active/returned in qs)
    orphans = [c for c in cats if c.id not in used_ids]
    if orphans:
        orphans = sorted(orphans, key=lambda x: (getattr(x, "sort_order", 0), x.name.lower(), x.id))
        groups.append(("Other", [(c.id, c.name) for c in orphans]))

    # Fallback: never return empty (Django handles empty, but this avoids weird UI)
    if not groups and cats:
        groups = [("Categories", [(c.id, c.name) for c in cats])]

    return groups


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
        ]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select", "size": 10}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "is_free": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Base queryset (active only, ordered for stable optgroups)
        base_qs = Category.objects.filter(is_active=True).order_by("type", "parent_id", "sort_order", "name", "id")

        # Kind-specific filtering (models vs files)
        kind_value = None
        if self.instance and self.instance.pk:
            kind_value = self.instance.kind
        else:
            kind_value = self.data.get("kind") or self.initial.get("kind")

        if kind_value in (Product.Kind.MODEL, Product.Kind.FILE):
            expected_type = Category.CategoryType.MODEL if kind_value == Product.Kind.MODEL else Category.CategoryType.FILE
            base_qs = base_qs.filter(type=expected_type)

        # Reduce scrolling: optgroup categories by parent and indent children
        # (Still uses a normal <select>, just organized better.)
        self.fields["category"].queryset = base_qs
        self.fields["category"].choices = _category_choices_for_form(base_qs)

        # Optional: make it a bit easier to scan (bigger dropdown) without being obnoxious
        self.fields["category"].widget.attrs.setdefault("class", "form-select")
        self.fields["category"].widget.attrs.setdefault("size", "10")  # shows more rows; still a dropdown

        self.fields["slug"].required = False

        # Nice-to-have: bootstrap classes for other fields if not already set in templates
        for name, f in self.fields.items():
            if name == "category":
                continue
            if isinstance(f.widget, (forms.TextInput, forms.Textarea, forms.NumberInput)):
                f.widget.attrs.setdefault("class", "form-control")
            elif isinstance(f.widget, (forms.Select,)):
                f.widget.attrs.setdefault("class", "form-select")
            elif isinstance(f.widget, (forms.CheckboxInput,)):
                f.widget.attrs.setdefault("class", "form-check-input")

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bootstrap-friendly defaults
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
    """
    Multi-image upload in one submit.

    IMPORTANT:
    - Do NOT use `multiple=True` in widget attrs or widget init.
    - Use a widget with allow_multiple_selected=True.
    """
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
        allowed = [t for t in preferred if t in ALLOWED_ASSET_EXTS] + sorted(t for t in ALLOWED_ASSET_EXTS if t not in preferred)

        if "file_type" in self.fields:
            self.fields["file_type"].choices = [(t, f".{t}") for t in allowed]
            self.fields["file_type"].required = True

        # Bootstrap defaults
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
