# config/settings/base.py

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-key-change-me")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = []

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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "home_craft_3d"),
        "USER": os.getenv("POSTGRES_USER", "hc3user"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "homecraftpass!"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

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

# ✅ Prevent dev/prod NameError
CSRF_TRUSTED_ORIGINS: list[str] = []

# -------- Cache (used by throttling) --------
CACHES = {
    "default": {
        "BACKEND": os.getenv("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "hc3-default"),
        "TIMEOUT": int(os.getenv("DJANGO_CACHE_TIMEOUT", "300")),
    }
}

# -------- reCAPTCHA v3 --------
RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "1").strip() not in ("0", "false", "False")
RECAPTCHA_V3_SITE_KEY = os.getenv("RECAPTCHA_V3_SITE_KEY", "").strip()
RECAPTCHA_V3_SECRET_KEY = os.getenv("RECAPTCHA_V3_SECRET_KEY", "").strip()
RECAPTCHA_V3_MIN_SCORE = float(os.getenv("RECAPTCHA_V3_MIN_SCORE", "0.5"))

# -------- Site base URL --------
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "").strip().rstrip("/")

# Stripe secrets remain env-based (NOT DB settings)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_PUBLISHABLE_KEY = STRIPE_PUBLIC_KEY

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_CONNECT_WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET")
