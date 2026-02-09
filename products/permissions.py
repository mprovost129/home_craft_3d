# products/permissions.py
from __future__ import annotations

from functools import wraps
from typing import Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def _get_profile(user):
    # Works with a typical OneToOne Profile named `profile`
    return getattr(user, "profile", None)


def is_owner_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    # Owner/admin override paths
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    profile = _get_profile(user)
    return bool(getattr(profile, "is_owner", False))


def is_seller_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_owner_user(user):
        return True
    profile = _get_profile(user)
    return bool(getattr(profile, "is_seller", False))


def seller_required(view_func: Callable[[HttpRequest, ...], HttpResponse]):
    """
    Requires:
      - authenticated
      - seller OR owner/admin
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not is_seller_user(request.user):
            return redirect(reverse("home"))
        return view_func(request, *args, **kwargs)

    return _wrapped
