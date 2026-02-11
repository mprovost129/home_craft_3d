# products/migrations/0016_product_download_count.py
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0015_remove_productphysical_depth_mm_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="download_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Total download actions for this product (bundle-level).",
            ),
        ),
    ]
