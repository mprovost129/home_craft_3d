# payments/models.py
from __future__ import annotations

import uuid
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils import timezone


def _sync_profile_stripe_fields(*, user, stripe_account_id: str, onboarding_complete: bool) -> None:
    """
    Keep accounts.Profile legacy fields synced with payments.SellerStripeAccount.

    We intentionally avoid importing Profile directly to prevent circular imports.
    """
    try:
        Profile = apps.get_model("accounts", "Profile")
    except Exception:
        return

    if not user:
        return

    # Update only the two legacy fields; do not touch role flags here.
    try:
        Profile.objects.filter(user=user).update(
            stripe_account_id=stripe_account_id or "",
            stripe_onboarding_complete=bool(onboarding_complete),
            updated_at=timezone.now(),
        )
    except Exception:
        # Best-effort; never break payments flow if profile update fails.
        return


class SellerStripeAccount(models.Model):
    """
    Stores Stripe Connect Express account linkage for a seller user.

    SOURCE OF TRUTH:
      - payments.SellerStripeAccount fields are authoritative
      - accounts.Profile.stripe_* fields are legacy mirrors for admin/UI convenience
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

    class Meta:
        indexes = [
            models.Index(fields=["stripe_account_id"]),
            models.Index(fields=["details_submitted", "charges_enabled", "payouts_enabled"]),
        ]

    def __str__(self) -> str:
        return f"SellerStripeAccount<{self.user_id}> {self.stripe_account_id or 'unlinked'}"

    @property
    def is_ready(self) -> bool:
        return bool(self.stripe_account_id) and self.details_submitted and self.charges_enabled and self.payouts_enabled

    def _sync_profile(self) -> None:
        _sync_profile_stripe_fields(
            user=self.user,
            stripe_account_id=self.stripe_account_id or "",
            onboarding_complete=self.is_ready,
        )

    def mark_onboarding_started(self) -> None:
        changed = False
        if not self.onboarding_started_at:
            self.onboarding_started_at = timezone.now()
            changed = True

        if changed:
            self.save(update_fields=["onboarding_started_at", "updated_at"])

        # Always mirror current account id + completion flag to Profile.
        self._sync_profile()

    def mark_onboarding_completed_if_ready(self) -> None:
        changed = False
        if self.is_ready and not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            changed = True

        if changed:
            self.save(update_fields=["onboarding_completed_at", "updated_at"])

        # Always mirror current truth to Profile.
        self._sync_profile()


class SellerFeeWaiver(models.Model):
    """
    Per-seller marketplace fee waiver window.
    During the window, marketplace cut is 0% (seller still pays Stripe fees).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_waiver",
    )

    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["ends_at"]),
        ]

    def __str__(self) -> str:
        return f"SellerFeeWaiver<{self.user_id}> {self.starts_at.date()} → {self.ends_at.date()}"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.starts_at <= now < self.ends_at

    @classmethod
    def ensure_for_seller(cls, *, user, waiver_days: int) -> "SellerFeeWaiver":
        """
        Create waiver if missing. Never shortens an existing waiver.
        """
        waiver_days = max(0, min(int(waiver_days or 0), 365))
        obj = cls.objects.filter(user=user).first()
        if obj:
            return obj

        starts = timezone.now()
        ends = starts + timedelta(days=waiver_days)
        return cls.objects.create(user=user, starts_at=starts, ends_at=ends)


class SellerBalanceEntry(models.Model):
    """
    Append-only ledger for seller balances.

    amount_cents:
      > 0  => platform owes seller
      < 0  => seller owes platform
    """

    class Reason(models.TextChoices):
        SALE = "sale", "Sale (order paid)"
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
        constraints = [
            models.UniqueConstraint(
                fields=["seller", "order", "reason"],
                name="uniq_seller_order_reason",
            )
        ]

    def __str__(self) -> str:
        return f"{self.seller_id}: {self.amount_cents} ({self.reason})"
