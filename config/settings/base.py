# config/settings/base.py

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import os

# Load environment variables from .env file
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def _db_from_database_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
    }


DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

if DATABASE_URL:
    DATABASES = {"default": _db_from_database_url(DATABASE_URL)}
else:
    # Local fallback
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "home_craft_3d"),
            "USER": os.getenv("POSTGRES_USER", "hc3user"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "homecraftpass!"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
        }
    }

# ============================================================
# Helpers
# ============================================================
def _csv_env(name: str, default: str = "") -> list[str]:
    """
    Read a comma-separated env var into a clean list.

    - Strips whitespace
    - Drops empty entries
    - Safe if unset/blank
    """
    raw = (os.getenv(name, default) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _bool_env(name: str, default: str = "False") -> bool:
    raw = (os.getenv(name, default) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ============================================================
# Core
# ============================================================
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "unsafe-dev-key-change-me"

# Allow either DEBUG or DJANGO_DEBUG in env
DEBUG = _bool_env("DEBUG", os.getenv("DJANGO_DEBUG", "False"))

# IMPORTANT: ALLOWED_HOSTS must NOT contain schemes.
# Example: "homecraft3d.onrender.com,homecraft3d.com,www.homecraft3d.com"
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", default="localhost,127.0.0.1,homecraft3d.onrender.com")

# IMPORTANT: CSRF_TRUSTED_ORIGINS MUST include scheme.
# Example: "https://homecraft3d.onrender.com,https://homecraft3d.com,https://www.homecraft3d.com"
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS", default="https://homecraft3d.onrender.com")


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS: list[str] = [
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "storages",
]

LOCAL_APPS = [
    "accounts.apps.AccountsConfig",
    "core.apps.CoreConfig",
    "catalog",
    "products",
    "cart",
    "orders",
    "payments",
    "reviews",
    "dashboards",
    "refunds.apps.RefundsConfig",
    "qa",
    "legal.apps.LegalConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.security_headers.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.sidebar_categories",
                "payments.context_processors.seller_stripe_status",
                "core.context_processors.sidebar_flags",
                "core.context_processors.site_config",
                "core.context_processors.analytics",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media: local in dev, S3 in prod (via STORAGES backend)
# MEDIA_URL should match storage backend to avoid hardcoding URLs
if _bool_env("USE_S3", "False"):
    # In production with S3, MEDIA_URL isn't used (storage.url() handles it)
    # But set it for consistency and any manual URL building
    MEDIA_URL = f"https://{(os.getenv('AWS_S3_MEDIA_BUCKET') or '').strip()}.s3.{(os.getenv('AWS_S3_REGION_NAME') or 'us-east-2').strip()}.amazonaws.com/media/"
else:
    # Local development: serve from /media/
    MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/profile/"
LOGOUT_REDIRECT_URL = "/"

SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True

# Production security settings for Render
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# -------- Cache (used by throttling) --------
CACHES = {
    "default": {
        "BACKEND": os.getenv("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "hc3-default"),
        "TIMEOUT": int(os.getenv("DJANGO_CACHE_TIMEOUT", "300")),
    }
}

# -------- reCAPTCHA v3 --------
RECAPTCHA_ENABLED = (os.getenv("RECAPTCHA_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no"))
RECAPTCHA_V3_SITE_KEY = os.getenv("RECAPTCHA_V3_SITE_KEY", "").strip()
RECAPTCHA_V3_SECRET_KEY = os.getenv("RECAPTCHA_V3_SECRET_KEY", "").strip()
RECAPTCHA_V3_MIN_SCORE = float(os.getenv("RECAPTCHA_V3_MIN_SCORE", "0.5"))

# -------- Site base URL --------
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "").strip().rstrip("/")

# -------- Analytics --------
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "").strip()

# Stripe secrets remain env-based (NOT DB settings)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_CONNECT_WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET")

# -------- Error reporting (Sentry) --------
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production" if not DEBUG else "development")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        integrations=[DjangoIntegration()],
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=True,
    )

# ------------------------------------------------------------------------------
# AWS S3 (optional)
# ------------------------------------------------------------------------------
USE_S3 = _bool_env("USE_S3", "False")

if USE_S3:
    AWS_ACCESS_KEY_ID = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    AWS_SECRET_ACCESS_KEY = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
    AWS_S3_REGION_NAME = (os.getenv("AWS_S3_REGION_NAME") or "us-east-2").strip()

    AWS_S3_MEDIA_BUCKET = (os.getenv("AWS_S3_MEDIA_BUCKET") or "").strip()
    AWS_S3_DOWNLOADS_BUCKET = (os.getenv("AWS_S3_DOWNLOADS_BUCKET") or "").strip()

    if not AWS_S3_MEDIA_BUCKET:
        raise RuntimeError("USE_S3=True but AWS_S3_MEDIA_BUCKET is not set.")
    if not AWS_S3_DOWNLOADS_BUCKET:
        raise RuntimeError("USE_S3=True but AWS_S3_DOWNLOADS_BUCKET is not set.")

    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

    # Signed URL defaults (downloads bucket uses signed URLs always)
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = int(os.getenv("AWS_S3_DOWNLOADS_QUERYSTRING_EXPIRE", "3600"))

    # Prefer modern Django storage config
    STORAGES = {
        "default": {"BACKEND": "core.storage_backends.MediaStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
