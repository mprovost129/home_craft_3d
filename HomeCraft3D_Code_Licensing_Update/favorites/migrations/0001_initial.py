from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("products", "0016_product_download_count"),
    ]

    operations = [
        migrations.CreateModel(
            name="Favorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorited_by",
                        to="products.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Favorite",
                "verbose_name_plural": "Favorites",
                "unique_together": {("user", "product")},
            },
        ),
        migrations.CreateModel(
            name="WishlistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wishlisted_by",
                        to="products.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wishlist_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Wishlist Item",
                "verbose_name_plural": "Wishlist Items",
                "unique_together": {("user", "product")},
            },
        ),
        migrations.AddIndex(
            model_name="favorite",
            index=models.Index(fields=["user", "created_at"], name="favorites_f_user_id_0cdd6a_idx"),
        ),
        migrations.AddIndex(
            model_name="favorite",
            index=models.Index(fields=["product", "created_at"], name="favorites_f_product_79d541_idx"),
        ),
        migrations.AddIndex(
            model_name="wishlistitem",
            index=models.Index(fields=["user", "created_at"], name="favorites_w_user_id_4e0f34_idx"),
        ),
        migrations.AddIndex(
            model_name="wishlistitem",
            index=models.Index(fields=["product", "created_at"], name="favorites_w_product_d714d9_idx"),
        ),
    ]
