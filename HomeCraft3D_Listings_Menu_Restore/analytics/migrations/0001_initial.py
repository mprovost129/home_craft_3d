from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalyticsEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("PAGEVIEW", "Pageview")], default="PAGEVIEW", max_length=32)),
                ("path", models.CharField(db_index=True, max_length=512)),
                ("method", models.CharField(default="GET", max_length=8)),
                ("status_code", models.PositiveIntegerField(default=200)),
                ("session_key", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("ip_hash", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("user_agent", models.CharField(blank=True, default="", max_length=400)),
                ("referrer", models.CharField(blank=True, db_index=True, default="", max_length=512)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="analytics_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["event_type", "created_at"], name="analytics_a_event_t_6eac2b_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["path", "created_at"], name="analytics_a_path_3c4bf9_idx"),
        ),
    ]
