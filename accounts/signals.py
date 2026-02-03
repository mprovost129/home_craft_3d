from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


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
        return

    Profile.objects.get_or_create(user=instance)