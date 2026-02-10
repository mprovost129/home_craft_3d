# qa/models.py
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductQuestionThread(models.Model):
    """A buyer-initiated Q&A thread for a product.

    Visibility: displayed on the product page.
    Posting: logged-in users only.
    Reply permissions: only thread.buyer and product.seller.
    """

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="qa_threads",
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="qa_threads",
        help_text="Thread starter (buyer).",
    )

    subject = models.CharField(max_length=180, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete (primarily for staff cleanup). When a product is unlisted, product detail is hidden anyway.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"QAThread<{self.pk}> product={self.product_id} buyer={self.buyer_id}"

    @property
    def is_deleted(self) -> bool:
        return bool(self.deleted_at)


class ProductQuestionMessage(models.Model):
    """A message within a thread.

    Soft-delete rules (locked spec):
      - author can delete within 30 minutes
      - after 30 minutes: staff only (upon request)

    Reports do NOT auto-hide (v1). Staff reviews via queue.
    """

    DELETE_WINDOW_MINUTES = 30

    thread = models.ForeignKey(
        ProductQuestionThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="qa_messages",
    )

    body = models.TextField()

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # soft delete
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="qa_messages_deleted",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["author", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"QAMessage<{self.pk}> thread={self.thread_id} author={self.author_id}"

    @property
    def is_deleted(self) -> bool:
        return bool(self.deleted_at)

    def can_author_delete_now(self) -> bool:
        if self.is_deleted:
            return False
        return timezone.now() - self.created_at <= timedelta(minutes=self.DELETE_WINDOW_MINUTES)


class ProductQuestionReport(models.Model):
    """Report record for a Q&A message.

    Locked spec:
      - dropdown reasons + optional text
      - never auto-hide in v1
      - staff queue for review
    """

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment"
        HATE = "hate", "Hate"
        VIOLENCE = "violence", "Violence"
        SEXUAL = "sexual", "Sexual content"
        ILLEGAL = "illegal", "Illegal content"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    message = models.ForeignKey(
        ProductQuestionMessage,
        on_delete=models.CASCADE,
        related_name="reports",
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="qa_reports",
    )

    reason = models.CharField(max_length=24, choices=Reason.choices)
    details = models.TextField(blank=True, default="")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="qa_reports_resolved",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["reporter", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"QAReport<{self.pk}> {self.status}"