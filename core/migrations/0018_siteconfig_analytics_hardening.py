from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_siteconfig_native_analytics"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_exclude_staff",
            field=models.BooleanField(default=True, help_text="If enabled, exclude staff/admin browsing from native analytics."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_exclude_admin_paths",
            field=models.BooleanField(default=True, help_text="If enabled, exclude /admin/ and /dashboard/ paths from native analytics."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_primary_host",
            field=models.CharField(blank=True, default="", help_text="Optional: restrict native analytics reports to this host (e.g. homecraft3d.com). Leave blank for all hosts.", max_length=255),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_primary_environment",
            field=models.CharField(blank=True, default="", help_text="Optional: restrict native analytics reports to this environment (e.g. production). Leave blank for all.", max_length=32),
        ),
    ]
