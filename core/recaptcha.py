# core/recaptcha.py
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecaptchaResult:
    ok: bool
    score: float
    action: str
    error: str


def _get_client_ip(request: HttpRequest) -> str:
    # If later behind a proxy, swap to X-Forwarded-For parsing
    return request.META.get("REMOTE_ADDR") or ""


def verify_recaptcha_v3(*, request: HttpRequest, token: str, expected_action: str) -> RecaptchaResult:
    """
    Verify reCAPTCHA v3 token against Google.

    Requires settings:
      - RECAPTCHA_V3_SECRET_KEY
      - RECAPTCHA_V3_MIN_SCORE (default 0.5)
      - RECAPTCHA_ENABLED (default True)
    """
    enabled = bool(getattr(settings, "RECAPTCHA_ENABLED", True))
    if not enabled:
        return RecaptchaResult(ok=True, score=1.0, action=expected_action, error="disabled")

    secret = (getattr(settings, "RECAPTCHA_V3_SECRET_KEY", "") or "").strip()
    if not secret:
        # Fail closed in prod, but don’t hard crash dev.
        logger.warning("RECAPTCHA_V3_SECRET_KEY missing; treating as failure.")
        return RecaptchaResult(ok=False, score=0.0, action="", error="recaptcha_not_configured")

    token = (token or "").strip()
    if not token:
        return RecaptchaResult(ok=False, score=0.0, action="", error="missing_token")

    data = urllib.parse.urlencode(
        {
            "secret": secret,
            "response": token,
            "remoteip": _get_client_ip(request),
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://www.google.com/recaptcha/api/siteverify",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as e:
        logger.exception("reCAPTCHA verification failed: %s", e)
        return RecaptchaResult(ok=False, score=0.0, action="", error="verify_error")

    success = bool(payload.get("success"))
    score = float(payload.get("score") or 0.0)
    action = str(payload.get("action") or "")
    min_score = float(getattr(settings, "RECAPTCHA_V3_MIN_SCORE", 0.5))

    if not success:
        return RecaptchaResult(ok=False, score=score, action=action, error="not_success")

    # v3 action must match or it’s likely scripted reuse
    if expected_action and action and action != expected_action:
        return RecaptchaResult(ok=False, score=score, action=action, error="action_mismatch")

    if score < min_score:
        return RecaptchaResult(ok=False, score=score, action=action, error="low_score")

    return RecaptchaResult(ok=True, score=score, action=action, error="")


def require_recaptcha_v3(action: str) -> Callable:
    """
    Decorator for POST endpoints. Expects token in POST:
      - "g-recaptcha-response" (common)
      - OR "recaptcha_token"
    """
    def decorator(view_func: Callable) -> Callable:
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.method != "POST":
                return view_func(request, *args, **kwargs)

            token = (request.POST.get("g-recaptcha-response") or request.POST.get("recaptcha_token") or "").strip()
            result = verify_recaptcha_v3(request=request, token=token, expected_action=action)

            if not result.ok:
                # Friendly UX
                messages.error(request, "We couldn’t verify you’re human. Please try again.")
                # safest redirect: back to referer, else home
                back = request.META.get("HTTP_REFERER") or "/"
                return redirect(back)

            return view_func(request, *args, **kwargs)

        wrapped.__name__ = getattr(view_func, "__name__", "wrapped")
        wrapped.__doc__ = getattr(view_func, "__doc__", "")
        return wrapped
    return decorator
