from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from products.models import ProductEngagementEvent


class Command(BaseCommand):
    help = "Delete ProductEngagementEvent rows older than N days (default: 90)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Delete events older than this many days (default: 90).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many rows would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days: int = options["days"]
        dry_run: bool = options["dry_run"]

        if days <= 0:
            self.stdout.write(self.style.ERROR("--days must be > 0"))
            return

        cutoff = timezone.now() - timedelta(days=days)
        qs = ProductEngagementEvent.objects.filter(created_at__lt=cutoff)

        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {count} engagement events older than {days} days (cutoff={cutoff.isoformat()})."
                )
            )
            return

        deleted_count, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} engagement events older than {days} days (cutoff={cutoff.isoformat()})."
            )
        )
