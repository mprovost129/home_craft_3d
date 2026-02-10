# accounts/services.py
from __future__ import annotations

import uuid

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify_email_and_in_app


def send_email_verification(*, request, user) -> None:
    """Send an email verification link and create an in-app notification.

    LOCKED: All email notifications should also create an in-app notification.
    """
    profile = getattr(user, "profile", None)
    if not profile:
        return

    # Ensure we have a token
    if not profile.email_verification_token:
        profile.email_verification_token = uuid.uuid4()

    profile.email_verification_sent_at = timezone.now()
    profile.save(update_fields=["email_verification_token", "email_verification_sent_at", "updated_at"])

    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email_confirm", kwargs={"token": str(profile.email_verification_token)})
    )

    ctx = {
        "user": user,
        "verify_url": verify_url,
        "site_name": getattr(settings, "SITE_NAME", "Home Craft 3D"),
    }

    notify_email_and_in_app(
        user=user,
        kind=Notification.Kind.VERIFICATION,
        email_subject="Verify your email · Home Craft 3D",
        email_template_html="accounts/emails/verify_email.html",
        email_template_txt="accounts/emails/verify_email.txt",
        context=ctx,
        title="Verify your email",
        body=f"Click the link to verify your email: {verify_url}",
        action_url=reverse("accounts:verify_email_status"),
        payload={"verify_url": verify_url},
    )
