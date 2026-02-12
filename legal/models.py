# legal/models.py
from __future__ import annotations

import hashlib
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class LegalDocument(models.Model):
        def formatted_body(self):
            """
            Returns the body with line breaks preserved for admin display.
            """
            from django.utils.html import format_html
            return format_html('<div style="white-space: pre-line;">{}</div>', self.body)
    """
    A versioned legal document displayed publicly (Terms, Privacy, etc).

    When content changes, a new version is created (not edited in place).
    """

    class DocType(models.TextChoices):
        TERMS = "terms", "Terms of Service"
        PRIVACY = "privacy", "Privacy Policy"
        REFUND = "refund", "Refund Policy"
        CONTENT = "content", "Content & Safety Policy"

        # Additional licensing / marketplace participation docs
        DIGITAL_LICENSE = "digital_license", "Digital Product License"
        SELLER_AGREEMENT = "seller_agreement", "Seller Agreement"
        PHYSICAL_POLICY = "physical_policy", "Physical Product Policy"
        SELLER_FEES = "seller_fees", "Seller Fees"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type = models.CharField(max_length=24, choices=DocType.choices)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    body = models.TextField(
        help_text="HTML is allowed. Content is rendered as trusted HTML (admin-only editing)."
    )
    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("doc_type", "version"),)
        indexes = [
            models.Index(fields=["doc_type", "is_published", "-version"]),
            models.Index(fields=["is_published", "-created_at"]),
        ]
        ordering = ["doc_type", "-version"]

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()} v{self.version} ({'published' if self.is_published else 'draft'})"

    @property
    def content_hash(self) -> str:
        """
        Stable fingerprint used to tie acceptances to exact content.
        """
        raw = f"{self.doc_type}|{self.version}|{self.title}|{self.body}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def clean(self):
        if not (self.title or "").strip():
            raise ValidationError({"title": "Title is required."})
        if not (self.body or "").strip():
            raise ValidationError({"body": "Body is required."})


class LegalAcceptance(models.Model):
    """
    Records acceptance of a specific LegalDocument version by a user or guest.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="acceptances")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="legal_acceptances",
    )
    guest_email = models.EmailField(blank=True, default="")

    accepted_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default="")

    # freeze the hash at acceptance time for auditability
    document_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "accepted_at"]),
            models.Index(fields=["guest_email", "accepted_at"]),
            models.Index(fields=["document", "accepted_at"]),
        ]
        ordering = ["-accepted_at"]

    def __str__(self) -> str:
        who = self.user_id or (self.guest_email or "guest")
        return f"Acceptance {who} -> {self.document.doc_type} v{self.document.version}"

    def clean(self):
        if not self.user_id and not (self.guest_email or "").strip():
            raise ValidationError("Either user or guest_email is required.")

    @property
    def is_guest(self) -> bool:
        return not bool(self.user_id)
