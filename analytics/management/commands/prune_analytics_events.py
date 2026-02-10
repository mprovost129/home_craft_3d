from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import AnalyticsEvent
from core.config import get_site_config


class Command(BaseCommand):
    help = "Prune old native analytics events based on SiteConfig.analytics_retention_days."

    def handle(self, *args, **options):
        cfg = get_site_config()
        days = int(getattr(cfg, "analytics_retention_days", 90) or 90)
        cutoff = timezone.now() - timedelta(days=days)
        qs = AnalyticsEvent.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} analytics events older than {days} days."))
