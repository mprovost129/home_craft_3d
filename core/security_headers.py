from __future__ import annotations

from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Lightweight baseline. Safe for dev; improves safety for prod.

    NOTE:
    - CSP defaults are intentionally "works-first".
    - Tighten CSP once templates/assets stabilize.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Stripe-friendly baseline CSP.
        # Override per environment with SECURITY_CSP if you want stricter rules.
        self.csp = getattr(
            settings,
            "SECURITY_CSP",
            "default-src 'self'; "
            "img-src 'self' data: blob: https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "script-src 'self' 'unsafe-inline' https://js.stripe.com https:; "
            "font-src 'self' https: data:; "
            "connect-src 'self' https://api.stripe.com https:; "
            "frame-src https://js.stripe.com https://hooks.stripe.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self';",
        )

        # Permissions-Policy: disable high-risk APIs by default
        self.permissions_policy = getattr(
            settings,
            "SECURITY_PERMISSIONS_POLICY",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )

        self.referrer_policy = getattr(
            settings,
            "SECURE_REFERRER_POLICY",
            "strict-origin-when-cross-origin",
        )

    def __call__(self, request):
        resp = self.get_response(request)

        # Clickjacking
        resp["X-Frame-Options"] = "DENY"

        # MIME sniffing
        resp["X-Content-Type-Options"] = "nosniff"

        # Referrer leakage
        resp["Referrer-Policy"] = self.referrer_policy

        # Modern browser XSS protection is handled by CSP. This disables legacy buggy behavior.
        resp["X-XSS-Protection"] = "0"

        # CSP
        resp["Content-Security-Policy"] = self.csp

        # Some sensible cross-origin defaults
        resp["Cross-Origin-Opener-Policy"] = "same-origin"
        resp["Cross-Origin-Resource-Policy"] = "same-origin"

        # Permissions policy
        resp["Permissions-Policy"] = self.permissions_policy

        # Only set HSTS when HTTPS is truly enforced.
        hsts_seconds = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
        if hsts_seconds > 0:
            include_sub = bool(getattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS", True))
            preload = bool(getattr(settings, "SECURE_HSTS_PRELOAD", False))

            value = f"max-age={hsts_seconds}"
            if include_sub:
                value += "; includeSubDomains"
            if preload:
                value += "; preload"

            resp["Strict-Transport-Security"] = value

        return resp
