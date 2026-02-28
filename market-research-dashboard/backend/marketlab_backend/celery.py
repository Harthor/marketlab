"""Celery application configuration for MarketLab.

Usage:
    celery -A marketlab_backend worker -l INFO -Q ingest,compute,alerts
    celery -A marketlab_backend beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

Redis broker assumed at localhost:6379/0 by default.
Override with CELERY_BROKER_URL env var.
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "marketlab_backend.settings")

app = Celery("marketlab")

# Read config from Django settings, namespace='CELERY'
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # type: ignore[no-untyped-def]
    """Simple debug task for verifying Celery connectivity."""
    print(f"Request: {self.request!r}")
