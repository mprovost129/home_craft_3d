# payments/models.py

from __future__ import annotations

import uuid

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

    stripe_account_id = models.CharField(
        max_length=255, blank=True, default="", db_index=True
    )

    details_submitted = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)

    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_account_id"]),
            models.Index(
                fields=["details_submitted", "charges_enabled", "payouts_enabled"]
            ),
        ]

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


class SellerBalanceEntry(models.Model):
    """
    Append-only ledger for seller balances.

    amount_cents:
      > 0  => platform owes seller
      < 0  => seller owes platform
    """

    class Reason(models.TextChoices):
        PAYOUT = "payout", "Payout"
        REFUND = "refund", "Refund"
        CHARGEBACK = "chargeback", "Chargeback"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance_entries",
    )

    amount_cents = models.IntegerField(
        help_text="Signed cents. Positive = owed to seller, negative = seller owes platform."
    )

    reason = models.CharField(max_length=32, choices=Reason.choices)

    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seller_balance_entries",
    )

    order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seller_balance_entries",
    )

    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["reason", "-created_at"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.seller_id}: {self.amount_cents} ({self.reason})"
