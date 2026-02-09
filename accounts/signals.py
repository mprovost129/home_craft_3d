# accounts/signals.py
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string

from notifications.models import Notification
from notifications.services import notify_email_and_in_app

from .models import Profile


def _site_base_url() -> str:
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip().rstrip("/")
    if base:
        return base
    return "http://localhost:8000"


def _absolute_static_url(path: str) -> str:
    base = _site_base_url().rstrip("/")
    static_url = (getattr(settings, "STATIC_URL", "/static/") or "/static/").strip()
    if not static_url.startswith("/"):
        static_url = f"/{static_url}"
    if not static_url.endswith("/"):
        static_url = f"{static_url}/"
    return f"{base}{static_url}{path.lstrip('/')}"


def _send_welcome_email(user) -> None:
    recipient = getattr(user, "email", "") or ""
    if not recipient:
        return

    subject = "Welcome to Home Craft 3D"
    logo_url = _absolute_static_url("images/homecraft3d_icon.svg")

    ctx = {
        "subject": subject,
        "logo_url": logo_url,
        "username": getattr(user, "username", "") or "",
        "profile_url": f"{_site_base_url()}/accounts/profile/",
        "shop_url": f"{_site_base_url()}/products/",
        "seller_url": f"{_site_base_url()}/payments/connect/start/",
    }

    # LOCKED: all emails also create in-app notifications.
    # Welcome email uses HTML template; plaintext is derived via strip_tags.
    notify_email_and_in_app(
        user=user,
        kind=Notification.Kind.SYSTEM,
        email_subject=subject,
        email_template_html="emails/welcome.html",
        email_template_txt=None,
        context=ctx,
        title="Welcome to Home Craft 3D",
        body="Welcome to Home Craft 3D!",
        action_url="/products/",
        payload={"type": "welcome"},
    )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_profile(sender, instance, created, **kwargs):
    """Ensure every user has a Profile.

    - On create: create Profile and seed a few fields from the User object.
    - On update: guarantee Profile exists (do not overwrite user-edited Profile fields).
    """

    if created:
        Profile.objects.create(
            user=instance,
            first_name=getattr(instance, "first_name", "") or "",
            last_name=getattr(instance, "last_name", "") or "",
            email=getattr(instance, "email", "") or "",
        )
        _send_welcome_email(instance)

        # Send admin notification email
        admin_email = getattr(settings, "ADMIN_NOTIFICATION_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", None))
        if admin_email:
            subject = "New User Signup - Home Craft 3D"
            body = f"A new user has signed up: {getattr(instance, 'username', '')} ({getattr(instance, 'email', '')})"
            try:
                send_mail(
                    subject,
                    body,
                    getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    [admin_email],
                )
            except Exception:
                pass
        return

    Profile.objects.get_or_create(user=instance)