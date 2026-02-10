# notifications/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Notification

User = get_user_model()


@dataclass(frozen=True)
class NotifyResult:
    notification_id: int
    email_sent: bool


def create_notification(
    *,
    user: User,
    kind: str,
    title: str,
    body: str,
    action_url: str = "",
    email_subject: str = "",
    email_text: str = "",
    email_html: str = "",
    email_template: str = "",
    payload: Optional[Mapping[str, Any]] = None,
) -> Notification:
    n = Notification(
        user=user,
        kind=kind,
        title=title or "",
        body=body or "",
        action_url=action_url or "",
        email_subject=email_subject or "",
        email_text=email_text or "",
        email_html=email_html or "",
        email_template=email_template or "",
        payload=dict(payload or {}),
    )
    n.full_clean()
    n.save()
    return n


def notify_in_app_only(
    *,
    user: User,
    kind: str,
    title: str,
    body: str,
    action_url: str = "",
    payload: Optional[Mapping[str, Any]] = None,
) -> Notification:
    return create_notification(
        user=user,
        kind=kind,
        title=title,
        body=body,
        action_url=action_url,
        payload=payload,
    )


def notify_email_and_in_app(
    *,
    user: User,
    kind: str,
    email_subject: str,
    email_template_html: str,
    email_template_txt: str | None = None,
    context: Mapping[str, Any],
    title: str = "",
    body: str = "",
    action_url: str = "",
    from_email: Optional[str] = None,
    reply_to: Optional[list[str]] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> NotifyResult:
    """
    One call that:
      1) creates in-app notification
      2) sends email (html+txt)

    This is the “single choke point” we’ll wire into existing email flows in the next change pack.
    """
    if not from_email:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "SERVER_EMAIL", "")

    # Render email bodies
    html_body = render_to_string(email_template_html, context)
    if email_template_txt:
        txt_body = render_to_string(email_template_txt, context)
    else:
        # Fallback: strip tags from HTML template.
        txt_body = strip_tags(html_body)

    # If title/body not provided, derive a reasonable in-app version
    derived_title = title.strip() if title else email_subject.strip()
    derived_body = body.strip() if body else txt_body.strip()

    with transaction.atomic():
        n = create_notification(
            user=user,
            kind=kind,
            title=derived_title[:160],
            body=derived_body,
            action_url=action_url,
            email_subject=email_subject[:200],
            email_text=txt_body,
            email_html=html_body,
            email_template=email_template_html,
            payload={
                **dict(payload or {}),
                "email_template_html": email_template_html,
                "email_template_txt": email_template_txt or "",
            },
        )

        email_sent = False
        try:
            msg = EmailMultiAlternatives(
                subject=email_subject,
                body=txt_body,
                from_email=from_email,
                to=[user.email],
                reply_to=reply_to or None,
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)
            email_sent = True
        except Exception as e:
            # Don’t roll back the in-app notification. Keep it as the audit trail.
            n.payload = {**n.payload, "email_error": repr(e)}
            n.save(update_fields=["payload"])

    return NotifyResult(notification_id=n.id, email_sent=email_sent)
