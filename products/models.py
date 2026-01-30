from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Product(models.Model):
    class Kind(models.TextChoices):
        MODEL = "MODEL", "3D Model (Physical)"
        FILE = "FILE", "3D File (Digital)"

    # Ownership / publishing
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        help_text="The user who owns this listing (seller).",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)

    # Core listing fields
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    short_description = models.CharField(max_length=280, blank=True)
    description = models.TextField(blank=True)

    # Category: must match the correct tree for kind (validated in clean())
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products",
    )

    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_free = models.BooleanField(default=False)

    # Visibility
    is_active = models.BooleanField(default=True)

    # Home page buckets (simple flags for MVP; can become computed later)
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)

    # Timestamps
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
        return f"{self.title} ({self.get_kind_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)

    def clean(self):
        """
        Enforce that product.kind matches the category tree type:
          - MODEL products must use Category.type = MODEL
          - FILE products must use Category.type = FILE
        """
        from django.core.exceptions import ValidationError
        from catalog.models import Category

        if self.category_id:
            if self.kind == Product.Kind.MODEL and self.category.type != Category.CategoryType.MODEL:
                raise ValidationError({"category": "Model products must use a 3D Models category."})
            if self.kind == Product.Kind.FILE and self.category.type != Category.CategoryType.FILE:
                raise ValidationError({"category": "File products must use a 3D Files category."})

        # price rules
        if self.is_free:
            self.price = Decimal("0.00")
        if not self.is_free and self.price <= Decimal("0.00"):
            # allow 0 only if free
            raise ValidationError({"price": "Price must be greater than $0.00 unless the item is marked free."})

    @property
    def display_price(self) -> str:
        if self.is_free:
            return "Free"
        return f"${self.price:,.2f}"

    def get_absolute_url(self) -> str:
        return reverse("products:detail", kwargs={"pk": self.pk, "slug": self.slug})

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()


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
        return f"Image<{self.product_id}>#{self.id}"


class ProductDigital(models.Model):
    """
    Extension table for digital file products.
    """
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="digital")

    # Optional fields (MVP)
    license_text = models.TextField(blank=True)
    file_count = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"Digital<{self.product_id}>"


class DigitalAsset(models.Model):
    """
    Individual downloadable asset (STL/OBJ/3MF/etc).
    In MVP we store the file; later we can gate download via paid orders.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="digital_assets")
    file = models.FileField(upload_to="digital_assets/")
    original_filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Asset<{self.product_id}>#{self.id}"


class ProductPhysical(models.Model):
    """
    Extension table for physical printed model products.
    """
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="physical")

    # MVP placeholders
    material = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=120, blank=True)
    width_mm = models.PositiveIntegerField(null=True, blank=True)
    height_mm = models.PositiveIntegerField(null=True, blank=True)
    depth_mm = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Physical<{self.product_id}>"
