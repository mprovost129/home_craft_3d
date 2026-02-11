from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_siteconfig_theme_accent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="home_hero_title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Home page hero headline (left side).",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="home_hero_subtitle",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Home page hero paragraph (left side).",
            ),
        ),
    ]
