# accounts/decorators.py
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


def email_verified_required(view_func):
    """Require a logged-in user with a verified email (Profile.email_verified)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return redirect("accounts:login")

        profile = getattr(user, "profile", None)
        if profile and getattr(profile, "email_verified", False):
            return view_func(request, *args, **kwargs)

        messages.warning(
            request,
            "Please verify your email to use this feature.",
        )
        return redirect(reverse("accounts:verify_email_status") + "?next=" + request.get_full_path())

    return _wrapped
