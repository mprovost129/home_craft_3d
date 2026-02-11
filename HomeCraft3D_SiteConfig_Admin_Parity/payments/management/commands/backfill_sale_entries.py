# payments/management/commands/backfill_sale_entries.py

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Order
from payments.models import SellerBalanceEntry


class Command(BaseCommand):
    help = "Backfill missing SellerBalanceEntry SALE credits for PAID orders."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of orders processed.")
        parser.add_argument("--order-id", type=str, default="", help="Process a single order UUID.")

    @transaction.atomic
    def handle(self, *args, **opts):
        dry_run: bool = bool(opts["dry_run"])
        limit: int = int(opts["limit"] or 0)
        order_id: str = (opts["order_id"] or "").strip()

        qs = Order.objects.filter(status=Order.Status.PAID).prefetch_related("items")
        if order_id:
            qs = qs.filter(pk=order_id)

        if limit > 0:
            qs = qs.order_by("-paid_at")[:limit]
        else:
            qs = qs.order_by("-paid_at")

        created = 0
        skipped = 0

        for order in qs:
            totals_by_seller: dict[str, int] = defaultdict(int)
            for it in order.items.all():
                seller_id = getattr(it, "seller_id", None)
                if not seller_id:
                    continue
                net = int(getattr(it, "seller_net_cents", 0) or 0)
                if net <= 0:
                    continue
                totals_by_seller[str(seller_id)] += net

            for seller_id, net_cents in totals_by_seller.items():
                if net_cents <= 0:
                    continue

                exists = SellerBalanceEntry.objects.filter(
                    seller_id=seller_id,
                    order=order,
                    reason=SellerBalanceEntry.Reason.SALE,
                ).exists()

                if exists:
                    skipped += 1
                    continue

                self.stdout.write(
                    f"[CREATE] order={order.pk} seller={seller_id} sale=+{net_cents}c"
                )

                if not dry_run:
                    SellerBalanceEntry.objects.create(
                        seller_id=seller_id,
                        order=order,
                        reason=SellerBalanceEntry.Reason.SALE,
                        amount_cents=int(net_cents),
                        note=f"Backfill SALE credit for paid order {order.pk}",
                    )
                created += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no changes written."))

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} skipped_existing={skipped}"))
