"""
Development settings.

These settings are for local development only.
"""

from .base import *
import os

# ------------------------------------------------------------------------------
# CORE
# ------------------------------------------------------------------------------

DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

# ------------------------------------------------------------------------------
# EMAIL (console backend for dev)
# ------------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ------------------------------------------------------------------------------
# SECURITY (relaxed for dev)
# ------------------------------------------------------------------------------

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ------------------------------------------------------------------------------
# LOGGING (simple console logging)
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
        "level": "INFO",
    },
}
