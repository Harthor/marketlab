"""Production settings — Fly.io with SQLite on persistent volume."""

import os

from .base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

# SQLite on Fly.io persistent volume
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/data/db.sqlite3",
    }
}

# Static files
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# CORS
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOW_ALL_ORIGINS = not CORS_ALLOWED_ORIGINS

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# API access token
API_ACCESS_TOKEN = os.environ.get("API_ACCESS_TOKEN", "")

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
