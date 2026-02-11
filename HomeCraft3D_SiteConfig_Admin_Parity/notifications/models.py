# notifications/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """
    In-app notification (mirrors an email and/or site event).

    Locked rules (per your decisions):
    - All email notifications should ALSO create an in-app notification.
    - Notifications should be labeled and separated by what it is for (verification, refund, password, etc.).
    - Notifications page shows the notification similar to what the email sent is.
    """

    class Kind(models.TextChoices):
        VERIFICATION = "VERIFICATION", "Verification"
        PASSWORD = "PASSWORD", "Password"
        REFUND = "REFUND", "Refund"
        ORDER = "ORDER", "Order"
        SELLER = "SELLER", "Seller"
        QNA = "QNA", "Q&A"
        REVIEW = "REVIEW", "Review"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )

    kind = models.CharField(
        max_length=32,
        choices=Kind.choices,
        default=Kind.SYSTEM,
        db_index=True,
        help_text="Category used to group/filter notifications (verification, refund, password, etc.).",
    )

    title = models.CharField(max_length=160, default="", blank=True)
    body = models.TextField(default="", blank=True)

    # Where to send the user when they click (e.g. order detail, refund request, verify page)
    action_url = models.CharField(max_length=400, default="", blank=True)

    # Optional: store the email subject/body metadata for “looks like the email” rendering
    email_subject = models.CharField(max_length=200, default="", blank=True)

    # Store the rendered email bodies so the in-app notification can look like the email.
    # This avoids relying on re-rendering templates later (templates may change).
    email_text = models.TextField(
        default="",
        blank=True,
        help_text="Rendered plain-text email body (if any).",
    )
    email_html = models.TextField(
        default="",
        blank=True,
        help_text="Rendered HTML email body (if any).",
    )

    # If you want to render HTML similar to email templates later
    email_template = models.CharField(
        max_length=200,
        default="",
        blank=True,
        help_text="Optional template name used to render the notification like an email.",
    )

    # Arbitrary JSON payload for future rendering/debugging
    payload = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_read", "created_at"]),
            models.Index(fields=["user", "kind", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.kind}] {self.title or 'Notification'} -> {self.user_id}"

    def mark_read(self, *, save: bool = True) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            if save:
                self.save(update_fields=["is_read", "read_at"])

    def mark_unread(self, *, save: bool = True) -> None:
        if self.is_read:
            self.is_read = False
            self.read_at = None
            if save:
                self.save(update_fields=["is_read", "read_at"])
