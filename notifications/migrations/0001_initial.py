# notifications/migrations/0001_initial.py
from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("VERIFICATION", "Verification"), ("PASSWORD", "Password"), ("REFUND", "Refund"), ("ORDER", "Order"), ("SELLER", "Seller"), ("QNA", "Q&A"), ("REVIEW", "Review"), ("SYSTEM", "System")], db_index=True, default="SYSTEM", help_text="Category used to group/filter notifications (verification, refund, password, etc.).", max_length=32)),
                ("title", models.CharField(blank=True, default="", max_length=160)),
                ("body", models.TextField(blank=True, default="")),
                ("action_url", models.CharField(blank=True, default="", max_length=400)),
                ("email_subject", models.CharField(blank=True, default="", max_length=200)),
                ("email_template", models.CharField(blank=True, default="", help_text="Optional template name used to render the notification like an email.", max_length=200)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "is_read", "created_at"], name="notificatio_user_id_4c3b0a_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "kind", "created_at"], name="notificatio_user_id_2c0c9d_idx"),
        ),
    ]
