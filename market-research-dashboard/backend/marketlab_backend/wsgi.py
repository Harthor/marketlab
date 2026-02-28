"""WSGI config for marketlab_backend project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marketlab_backend.settings.local')

application = get_wsgi_application()
