"""
Production settings.

These settings are for the live environment.
"""

from .base import *
import os

# ------------------------------------------------------------------------------
# CORE
# ------------------------------------------------------------------------------

DEBUG = False

ALLOWED_HOSTS = [
    "homecraft3d.com",      # change to real domain
    "www.homecraft3d.com",  # change to real domain
]

# ------------------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------------------

SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = "DENY"

# ------------------------------------------------------------------------------
# EMAIL (real backend required)
# ------------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@homecraft3d.com")

# ------------------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
