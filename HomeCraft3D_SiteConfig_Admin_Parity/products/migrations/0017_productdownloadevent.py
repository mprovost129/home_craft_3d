# products/migrations/0017_productdownloadevent.py
from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0016_product_download_count"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductDownloadEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(blank=True, default="", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="download_events", to="products.product"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="product_download_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="productdownloadevent",
            index=models.Index(fields=["product", "created_at"], name="products_pr_product__9b3f4b_idx"),
        ),
        migrations.AddIndex(
            model_name="productdownloadevent",
            index=models.Index(fields=["product", "user", "created_at"], name="products_pr_product__a8c9c6_idx"),
        ),
        migrations.AddIndex(
            model_name="productdownloadevent",
            index=models.Index(fields=["product", "session_key", "created_at"], name="products_pr_product__6d3e74_idx"),
        ),
    ]
