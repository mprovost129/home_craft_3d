from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_siteconfig_google_analytics_dashboard_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_enabled",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, record lightweight pageview analytics for the admin dashboard.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="analytics_retention_days",
            field=models.PositiveIntegerField(
                default=90,
                help_text="How many days of analytics events to retain (pruned by management command).",
            ),
        ),
    ]
