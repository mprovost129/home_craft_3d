# products/models.py
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.storage_backends import get_downloads_storage


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


# --- defaults (can be overridden in settings) ---
DEFAULT_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
DEFAULT_ASSET_EXTS = {"stl", "obj", "3mf", "zip"}

MAX_IMAGE_MB = _get_setting_int("HC3_MAX_IMAGE_MB", 8)
MAX_ASSET_MB = _get_setting_int("HC3_MAX_ASSET_MB", 200)

ALLOWED_IMAGE_EXTS = _get_setting_set("HC3_ALLOWED_IMAGE_EXTS", DEFAULT_IMAGE_EXTS)
ALLOWED_ASSET_EXTS = _get_setting_set("HC3_ALLOWED_ASSET_EXTS", DEFAULT_ASSET_EXTS)


def _validate_uploaded_file(*, f, allowed_exts: set[str], max_mb: int, field_label: str) -> None:
    if not f:
        return
    name = getattr(f, "name", "") or ""
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in allowed_exts:
        raise ValidationError({field_label: f"Unsupported file type .{ext or '?'}"})

    size = getattr(f, "size", None)
    if size is not None:
        limit_bytes = int(max_mb) * 1024 * 1024
        if int(size) > limit_bytes:
            raise ValidationError({field_label: f"File too large. Max {max_mb} MB."})


def _extract_zip_contents(file_obj, *, limit: int = 200) -> list[str]:
    if not file_obj:
        return []

    fh = None
    try:
        fh = file_obj.open("rb")
    except Exception:
        try:
            fh = file_obj
        except Exception:
            return []

    try:
        with zipfile.ZipFile(fh) as zf:
            names = [
                n
                for n in zf.namelist()
                if n and not n.endswith("/") and not n.startswith("__MACOSX/")
            ]
            return names[:limit]
    except Exception:
        return []
    finally:
        try:
            if fh is not file_obj:
                fh.close()
        except Exception:
            pass


class Product(models.Model):
    class Kind(models.TextChoices):
        MODEL = "MODEL", "3D Model (Physical)"
        FILE = "FILE", "3D File (Digital)"

    class ComplexityLevel(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        help_text="The user who owns this listing (seller).",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    short_description = models.CharField(max_length=280, blank=True)
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products",
    )
    subcategory = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products_subcategory",
        null=True,
        blank=True,
        help_text="Subcategory under the main category."
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_free = models.BooleanField(default=False)


    max_purchases_per_buyer = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of times a single buyer can purchase this product. Leave blank for no limit."
    )

    # Draft-first default:
    is_active = models.BooleanField(default=False)

    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)

    complexity_level = models.CharField(
        max_length=20,
        choices=ComplexityLevel.choices,
        blank=True,
        null=True,
        help_text="Difficulty level for this 3D file/model",
    )
    print_time_hours = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Estimated print time in hours",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("seller", "slug"),)
        indexes = [
            models.Index(fields=["kind", "is_active", "created_at"]),
            models.Index(fields=["is_featured", "is_active"]),
            models.Index(fields=["is_trending", "is_active"]),
            models.Index(fields=["slug"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_kind_display()})"  # type: ignore[attr-defined]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)

    def clean(self):
        from catalog.models import Category

        if self.category_id:
            if self.kind == Product.Kind.MODEL and self.category.type != Category.CategoryType.MODEL:
                raise ValidationError({"category": "Model products must use a 3D Models category."})
            if self.kind == Product.Kind.FILE and self.category.type != Category.CategoryType.FILE:
                raise ValidationError({"category": "File products must use a 3D Files category."})

        if self.is_free:
            self.price = Decimal("0.00")
        if not self.is_free and self.price <= Decimal("0.00"):
            raise ValidationError({"price": "Price must be greater than $0.00 unless the item is marked free."})

        if self.max_purchases_per_buyer is not None and self.max_purchases_per_buyer < 1:
            raise ValidationError({"max_purchases_per_buyer": "If set, must be at least 1."})

    @property
    def display_price(self) -> str:
        return "Free" if self.is_free else f"${self.price:,.2f}"

    def get_absolute_url(self) -> str:
        return reverse("products:detail", kwargs={"pk": self.pk, "slug": self.slug})

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.order_by("sort_order", "id").first()

    @property
    def has_specs(self) -> bool:
        if self.kind == self.Kind.MODEL:
            try:
                physical = self.physical
            except Exception:
                return False

            return any(
                [
                    (physical.material or "").strip(),
                    (physical.color or "").strip(),
                    physical.num_colors,
                    physical.width_mm,
                    physical.height_mm,
                    physical.depth_mm,
                    physical.weight_grams,
                    bool(physical.support_required),
                    (physical.specifications or "").strip(),
                ]
            )

        if self.kind == self.Kind.FILE:
            try:
                digital = self.digital
            except Exception:
                return False

            return any(
                [
                    (digital.software_requirements or "").strip(),
                    (digital.compatible_software or "").strip(),
                    (digital.license_type or "").strip(),
                    (digital.requirements or "").strip(),
                    (digital.license_text or "").strip(),
                ]
            )

        return False

    @property
    def seller_public_name(self) -> str:
        try:
            profile = self.seller.profile
        except Exception:
            profile = None
        if profile is not None:
            try:
                name = (profile.shop_name or "").strip()
                if name:
                    return name
            except Exception:
                pass
        return getattr(self.seller, "username", "Seller")

    def file_types(self) -> list[str]:
        types: set[str] = set()
        for asset in self.digital_assets.all():
            if asset.file_type:
                types.add(str(asset.file_type).lower().lstrip("."))
            else:
                name = getattr(asset.file, "name", "") or ""
                ext = Path(name).suffix.lower().lstrip(".")
                if ext:
                    types.add(ext)

        preferred = ["stl", "3mf", "obj", "zip"]
        ordered = [t for t in preferred if t in types] + sorted(t for t in types if t not in preferred)
        return [f".{t}" for t in ordered]

    @property
    def file_types_display(self) -> str:
        return ", ".join(self.file_types())


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="product_images/")
    alt_text = models.CharField(max_length=160, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["product", "is_primary", "sort_order"]),
        ]
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"Image<{self.product_id}>#{self.pk}"

    def clean(self):
        super().clean()
        _validate_uploaded_file(
            f=self.image,
            allowed_exts=ALLOWED_IMAGE_EXTS,
            max_mb=MAX_IMAGE_MB,
            field_label="image",
        )


class ProductDigital(models.Model):
    class LicenseType(models.TextChoices):
        PERSONAL = "personal", "Personal Use Only"
        COMMERCIAL = "commercial", "Commercial Use Allowed"
        EDUCATIONAL = "educational", "Educational Use"
        OPEN_SOURCE = "open_source", "Open Source / CC License"
    
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="digital")
    license_text = models.TextField(blank=True)
    file_count = models.PositiveIntegerField(default=0)
    
    # Digital specs
    software_requirements = models.CharField(max_length=255, blank=True, help_text="e.g., Fusion 360, FreeCAD, Blender")
    compatible_software = models.CharField(max_length=255, blank=True, help_text="e.g., Windows, macOS, Linux")
    license_type = models.CharField(max_length=20, choices=LicenseType.choices, blank=True, help_text="Usage rights for this file")
    requirements = models.TextField(blank=True, help_text="System requirements, dependencies, installation notes, etc.")

    def __str__(self) -> str:
        return f"Digital<{self.product_id}>"


class DigitalAsset(models.Model):
    """
    Individual downloadable asset (STL/OBJ/3MF/ZIP).
    Routed to the downloads bucket when USE_S3=True.
    """

    class FileType(models.TextChoices):
        STL = "stl", ".stl"
        THREE_MF = "3mf", ".3mf"
        OBJ = "obj", ".obj"
        ZIP = "zip", ".zip"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="digital_assets")

    # downloads storage (S3 downloads bucket when USE_S3=True)
    file = models.FileField(upload_to="digital_assets/", storage=get_downloads_storage())

    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=10, choices=FileType.choices, blank=True, null=True)
    zip_contents = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Asset<{self.product_id}>#{self.pk}"

    def clean(self):
        super().clean()
        _validate_uploaded_file(
            f=self.file,
            allowed_exts=ALLOWED_ASSET_EXTS,
            max_mb=MAX_ASSET_MB,
            field_label="file",
        )
        name = getattr(self.file, "name", "") or ""
        ext = Path(name).suffix.lower().lstrip(".")
        if not self.file_type and ext:
            self.file_type = ext
        if self.file_type and ext and self.file_type.lower() != ext:
            raise ValidationError({"file_type": "Selected file type does not match file extension."})
        is_zip = (self.file_type or ext) == "zip"
        if is_zip:
            self.zip_contents = _extract_zip_contents(self.file)
        else:
            self.zip_contents = None


class ProductPhysical(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="physical")

    material = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=120, blank=True)
    num_colors = models.PositiveIntegerField(null=True, blank=True, help_text="Number of colors in this print")
    width_mm = models.PositiveIntegerField(null=True, blank=True)
    height_mm = models.PositiveIntegerField(null=True, blank=True)
    depth_mm = models.PositiveIntegerField(null=True, blank=True)
    weight_grams = models.PositiveIntegerField(null=True, blank=True, help_text="Weight in grams")
    support_required = models.BooleanField(default=False, help_text="Does this model require supports for printing?")
    specifications = models.TextField(blank=True, help_text="Additional specifications (e.g., scale info, assembly instructions, etc.)")

    def __str__(self) -> str:
        return f"Physical<{self.product_id}>"


class ProductEngagementEvent(models.Model):
    class EventType(models.TextChoices):
        VIEW = "VIEW", "View"
        ADD_TO_CART = "ADD_TO_CART", "Add to cart"
        CLICK = "CLICK", "Click"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="engagement_events",
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["product", "event_type", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} product={self.product_id} at {self.created_at}"
