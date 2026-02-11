from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="analyticsevent",
            name="visitor_id",
            field=models.CharField(blank=True, db_index=True, default="", help_text="Stable first-party visitor id (hc_vid cookie).", max_length=36),
        ),
        migrations.AddField(
            model_name="analyticsevent",
            name="session_id",
            field=models.CharField(blank=True, db_index=True, default="", help_text="Session id (hc_sid cookie). Rotates after inactivity window.", max_length=36),
        ),
        migrations.AddField(
            model_name="analyticsevent",
            name="host",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="analyticsevent",
            name="environment",
            field=models.CharField(blank=True, db_index=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="analyticsevent",
            name="is_staff",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="analyticsevent",
            name="is_bot",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["visitor_id", "created_at"], name="analytics_v_vid_created_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["session_id", "created_at"], name="analytics_v_sid_created_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["host", "created_at"], name="analytics_v_host_created_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["environment", "created_at"], name="analytics_v_env_created_idx"),
        ),
    ]
