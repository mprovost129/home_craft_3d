from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SellerStripeAccount(models.Model):
    """
    Stores Stripe Connect Express account linkage for a seller user.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stripe_connect",
    )

    stripe_account_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    details_submitted = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)

    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"SellerStripeAccount<{self.user_id}> {self.stripe_account_id or 'unlinked'}"

    @property
    def is_ready(self) -> bool:
        return bool(self.stripe_account_id) and self.details_submitted and self.charges_enabled and self.payouts_enabled

    def mark_onboarding_started(self) -> None:
        if not self.onboarding_started_at:
            self.onboarding_started_at = timezone.now()
            self.save(update_fields=["onboarding_started_at", "updated_at"])

    def mark_onboarding_completed_if_ready(self) -> None:
        if self.is_ready and not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            self.save(update_fields=["onboarding_completed_at", "updated_at"])
