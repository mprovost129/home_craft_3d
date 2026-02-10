from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewReply",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "review",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reply",
                        to="reviews.review",
                    ),
                ),
                (
                    "seller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_replies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reviewreply",
            index=models.Index(fields=["seller", "created_at"], name="reviews_repl_seller__b0a2c2_idx"),
        ),
    ]
