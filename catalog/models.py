from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    class CategoryType(models.TextChoices):
        MODEL = "MODEL", "3D Models"
        FILE = "FILE", "3D Files"

    type = models.CharField(max_length=10, choices=CategoryType.choices)

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)

    # Root categories have parent = NULL.
    # Subcategories have parent = a root Category.
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("type", "parent", "slug"),)
        indexes = [
            models.Index(fields=["type", "is_active", "sort_order"]),
            models.Index(fields=["parent", "is_active", "sort_order"]),
            models.Index(fields=["slug"]),
        ]
        # Alphabetical-first:
        # - groups by type (Models vs Files)
        # - groups by parent so children are grouped under their parent in general queries
        # - alphabetizes by name
        ordering = ["type", "parent_id", "name"]

    def __str__(self) -> str:
        if self.parent:
            return f"{self.get_type_display()} :: {self.parent.name} > {self.name}"
        return f"{self.get_type_display()} :: {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    def get_absolute_url(self) -> str:
        return reverse("catalog:category_detail", kwargs={"pk": self.pk})


# -----------------------------
# Admin UX: Category vs Subcategory
# Proxy models (NO DB changes)
# -----------------------------

class RootCategory(Category):
    class Meta:
        proxy = True
        verbose_name = "Category"
        verbose_name_plural = "Categories"


class SubCategory(Category):
    class Meta:
        proxy = True
        verbose_name = "Subcategory"
        verbose_name_plural = "Subcategories"
