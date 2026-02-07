# config/settings/prod.py
"""
Production settings.

These settings are for the live environment.
"""

from .base import *  # noqa
import os

# ------------------------------------------------------------------------------
# CORE
# ------------------------------------------------------------------------------

DEBUG = False

ALLOWED_HOSTS = ["homecraft3d.com", "www.homecraft3d.com", "homecraft3d.onrender.com"]

CSRF_TRUSTED_ORIGINS = ["https://homecraft3d.com", "https://www.homecraft3d.com", "https://homecraft3d.onrender.com"]

# ------------------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------------------

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SESSION_COOKIE_DOMAIN = ".homecraft3d.com"
CSRF_COOKIE_DOMAIN = ".homecraft3d.com"

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# If you're behind a reverse proxy / load balancer:
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Throttling should trust proxy headers only when you control them.
THROTTLE_TRUST_PROXY_HEADERS = True

# ------------------------------------------------------------------------------
# EMAIL (real backend required)
# ------------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in ("1", "true", "yes", "on")

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "homecraft3dstore@gmail.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "homecraft3dstore@gmail.com")

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
