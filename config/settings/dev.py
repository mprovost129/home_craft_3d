# config/settings/dev.py
"""
Development settings.
These settings are for local development only.
"""

from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "homecraft3d.onrender.com"
]

CSRF_TRUSTED_ORIGINS = [
    # keep empty for localhost; add ngrok/cloudflare tunnel here if used
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
