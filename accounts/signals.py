from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_profile(sender, instance, created, **kwargs):
    """
    Ensure every user has a Profile. Keeps the app resilient even if users are created in admin.
    """
    if created:
        Profile.objects.create(
            user=instance,
            first_name=getattr(instance, "first_name", "") or "",
            last_name=getattr(instance, "last_name", "") or "",
            email=getattr(instance, "email", "") or "",
        )
    else:
        # If profile exists, do nothing; if missing, create it.
        Profile.objects.get_or_create(user=instance)
