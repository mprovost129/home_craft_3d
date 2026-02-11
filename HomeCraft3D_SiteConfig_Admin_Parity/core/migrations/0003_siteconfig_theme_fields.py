from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_siteconfig_facebook_url_siteconfig_instagram_url_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="theme_default_mode",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark")],
                default="light",
                help_text="Default color mode for new visitors (users may toggle).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_primary",
            field=models.CharField(default="#F97316", help_text="Primary action color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_accent",
            field=models.CharField(default="#F97316", help_text="Accent color (hex). Often same as primary for a tight brand.", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_success",
            field=models.CharField(default="#16A34A", help_text="Success color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_danger",
            field=models.CharField(default="#DC2626", help_text="Danger color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_light_bg",
            field=models.CharField(default="#F9FAFB", help_text="Light mode page background (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_light_surface",
            field=models.CharField(default="#FFFFFF", help_text="Light mode surface/card background (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_light_text",
            field=models.CharField(default="#111827", help_text="Light mode text color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_light_text_muted",
            field=models.CharField(default="#6B7280", help_text="Light mode muted text (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_light_border",
            field=models.CharField(default="#E5E7EB", help_text="Light mode border color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_dark_bg",
            field=models.CharField(default="#0B1220", help_text="Dark mode page background (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_dark_surface",
            field=models.CharField(default="#111B2E", help_text="Dark mode surface/card background (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_dark_text",
            field=models.CharField(default="#EAF0FF", help_text="Dark mode text color (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_dark_text_muted",
            field=models.CharField(default="#9FB0D0", help_text="Dark mode muted text (hex).", max_length=20),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="theme_dark_border",
            field=models.CharField(default="#22304D", help_text="Dark mode border color (hex).", max_length=20),
        ),
    ]
