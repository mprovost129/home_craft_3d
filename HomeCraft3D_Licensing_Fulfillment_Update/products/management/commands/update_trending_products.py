# products/management/commands/update_trending_products.py
"""
Update trending products based on recent engagement (views).

Marks products as trending if they have high engagement in the last 7 days.
Run periodically (e.g., via celery beat or cron): every 6 hours.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from products.models import Product, ProductEngagementEvent


class Command(BaseCommand):
    help = "Update trending products based on recent engagement metrics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to look back for engagement (default: 7)",
        )
        parser.add_argument(
            "--top-count",
            type=int,
            default=20,
            help="Number of products to mark as trending (default: 20)",
        )
        parser.add_argument(
            "--min-views",
            type=int,
            default=5,
            help="Minimum views required to be considered for trending (default: 5)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        top_count = options["top_count"]
        min_views = options["min_views"]

        cutoff_date = timezone.now() - timedelta(days=days)

        # Get engagement events from the past N days
        recent_events = ProductEngagementEvent.objects.filter(
            created_at__gte=cutoff_date,
            event_type=ProductEngagementEvent.EventType.VIEW,
        )

        # Count views per product
        view_counts = (
            recent_events.values("product_id")
            .annotate(view_count=models.Count("id"))
            .filter(view_count__gte=min_views)
            .order_by("-view_count")[: top_count]
        )

        trending_product_ids = [item["product_id"] for item in view_counts]

        # Mark trending products
        Product.objects.filter(id__in=trending_product_ids).update(is_trending=True)

        # Unmark non-trending products
        Product.objects.exclude(id__in=trending_product_ids).update(is_trending=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Updated trending products: {len(trending_product_ids)} products "
                f"marked as trending (based on {days} days, min {min_views} views)"
            )
        )

        # Show top products
        if trending_product_ids:
            top_products = Product.objects.filter(id__in=trending_product_ids[:5])
            self.stdout.write("\nTop trending products:")
            for i, product in enumerate(top_products, 1):
                view_count = next(
                    (item["view_count"] for item in view_counts if item["product_id"] == product.id),
                    0,
                )
                self.stdout.write(f"  {i}. {product.title} ({view_count} views)")
