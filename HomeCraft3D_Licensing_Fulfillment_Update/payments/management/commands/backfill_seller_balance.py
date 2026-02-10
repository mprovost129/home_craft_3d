from django.core.management.base import BaseCommand
from orders.models import Order
from payments.models import SellerBalanceEntry
from django.db import transaction

class Command(BaseCommand):
    help = "Backfill SellerBalanceEntry for all paid orders that are missing them."

    def handle(self, *args, **options):
        count_created = 0
        with transaction.atomic():
            paid_orders = Order.objects.filter(status=Order.Status.PAID)
            for order in paid_orders:
                for item in order.items.all():
                    exists = SellerBalanceEntry.objects.filter(order_item=item, reason=SellerBalanceEntry.Reason.ADJUSTMENT).exists()
                    if not exists:
                        SellerBalanceEntry.objects.create(
                            seller=item.seller,
                            amount_cents=item.seller_net_cents,
                            reason=SellerBalanceEntry.Reason.ADJUSTMENT,
                            order=order,
                            order_item=item,
                            note=f"Backfill: Order paid {order.pk} (item {item.pk})"
                        )
                        count_created += 1
        self.stdout.write(self.style.SUCCESS(f"Backfilled {count_created} SellerBalanceEntry records."))
