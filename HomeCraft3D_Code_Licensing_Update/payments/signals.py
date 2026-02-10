# payments/signals.py
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from payments.models import SellerStripeAccount
from payments.services_fee_waiver import ensure_fee_waiver_for_new_seller


@receiver(post_save, sender=SellerStripeAccount)
def _start_fee_waiver_when_stripe_row_created(sender, instance: SellerStripeAccount, created: bool, **kwargs):
    """
    Practical trigger: when a SellerStripeAccount row exists, we treat the user as a seller.
    That lets us automatically start the waiver without depending on user/profile role plumbing.

    If your "seller role" is tracked elsewhere (e.g., profile.is_seller), we can move this signal
    to that model instead. This works immediately with what you already have.
    """
    if created:
        ensure_fee_waiver_for_new_seller(seller_user=instance.user)
