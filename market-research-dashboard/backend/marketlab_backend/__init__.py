"""Market Research Dashboard Django project package."""

# Ensure the Celery app is loaded when Django starts
# so that @shared_task decorators are registered.
try:
    from .celery import app as celery_app  # noqa: F401

    __all__ = ("celery_app",)
except ImportError:
    # Celery not installed — skip (dev/test without worker)
    pass
