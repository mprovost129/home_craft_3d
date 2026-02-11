from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_rename_notificatio_user_id_4c3b0a_idx_notificatio_user_id_8a7c6b_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="email_text",
            field=models.TextField(
                default="",
                blank=True,
                help_text="Rendered plain-text email body (if any).",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="email_html",
            field=models.TextField(
                default="",
                blank=True,
                help_text="Rendered HTML email body (if any).",
            ),
        ),
    ]
