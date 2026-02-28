"""Local development settings — SQLite, DEBUG=True, permissive CORS."""

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db.sqlite3"),  # noqa: F405
    }
}

CORS_ALLOW_ALL_ORIGINS = True
