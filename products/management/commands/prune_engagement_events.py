from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from products.models import ProductEngagementEvent


class Command(BaseCommand):
    help = "Delete old ProductEngagementEvent rows older than N days (default 90)."

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
        parser.add_argument(
            "--chunk",
            type=int,
            default=5000,
            help="Delete in chunks of this size to avoid long locks (default: 5000).",
        )

    def handle(self, *args, **options):
        days: int = options["days"]
        dry_run: bool = options["dry_run"]
        chunk: int = options["chunk"]

        cutoff = timezone.now() - timedelta(days=days)

        qs = ProductEngagementEvent.objects.filter(created_at__lt=cutoff).order_by("id")
        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No engagement events to prune."))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {total} engagement events older than {days} days (cutoff={cutoff})."
                )
            )
            return

        deleted = 0
        while True:
            ids = list(qs.values_list("id", flat=True)[:chunk])
            if not ids:
                break
            ProductEngagementEvent.objects.filter(id__in=ids).delete()
            deleted += len(ids)
            self.stdout.write(f"Deleted {deleted}/{total}...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Pruned {deleted} engagement events older than {days} days (cutoff={cutoff})."
            )
        )
