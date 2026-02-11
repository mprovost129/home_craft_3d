# orders/management/commands/send_download_reminders.py
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order, OrderEvent, _send_download_reminder_email


class Command(BaseCommand):
    help = "Send download reminder emails for paid digital orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Minimum age in days since payment before sending reminders (default: 3).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum number of reminders to send in one run (default: 200).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show how many reminders would be sent.",
        )

    def handle(self, *args, **options):
        days = int(options.get("days") or 3)
        limit = int(options.get("limit") or 200)
        dry_run = bool(options.get("dry_run"))

        cutoff = timezone.now() - timedelta(days=days)

        qs = (
            Order.objects.filter(status=Order.Status.PAID, paid_at__lte=cutoff)
            .filter(kind__in=[Order.Kind.DIGITAL, Order.Kind.MIXED])
            .order_by("paid_at")
        )

        candidates = []
        for order in qs:
            if not order.items.filter(is_digital=True).exists():  # type: ignore[attr-defined]
                continue

            already_sent = order.events.filter(  # type: ignore[attr-defined]
                type=OrderEvent.Type.WARNING,
                message="Download reminder sent",
            ).exists()
            if already_sent:
                continue

            candidates.append(order)
            if len(candidates) >= limit:
                break

        if dry_run:
            self.stdout.write(f"{len(candidates)} reminder(s) would be sent.")
            return

        sent = 0
        for order in candidates:
            if _send_download_reminder_email(order):
                OrderEvent.objects.create(
                    order=order,
                    type=OrderEvent.Type.WARNING,
                    message="Download reminder sent",
                )
                sent += 1

        self.stdout.write(f"Sent {sent} download reminder(s).")
