import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


def _workspace_root() -> Path:
    raw_path = os.getenv("MARKETLAB_WORKSPACE", str(BASE_DIR.parent))
    return Path(raw_path).expanduser().resolve()


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-marketlab-secret')
DEBUG = _env_bool('MARKETLAB_DEBUG', True)
raw_hosts = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in raw_hosts.split(',') if host.strip()] if raw_hosts else ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.messages',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'api',
    'paper_trading',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'marketlab_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'marketlab_backend.wsgi.application'
ASGI_APPLICATION = 'marketlab_backend.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(BASE_DIR / 'db.sqlite3'),
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    cors_origins = [
        origin.strip()
        for origin in os.getenv('MARKETLAB_CORS_ORIGINS', '').split(',')
        if origin.strip()
    ]
    CORS_ALLOWED_ORIGINS = cors_origins

MARKETLAB_WORKSPACE = _workspace_root()

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Route tasks to dedicated queues
CELERY_TASK_ROUTES = {
    "api.tasks.ingest_*": {"queue": "ingest"},
    "api.tasks.compute_*": {"queue": "compute"},
    "api.tasks.alert_*": {"queue": "alerts"},
}

# Default queue for tasks without explicit routing
CELERY_TASK_DEFAULT_QUEUE = "ingest"

# Beat schedule — all periodic tasks
from celery.schedules import crontab  # noqa: E402, I001

CELERY_BEAT_SCHEDULE = {
    # -- Ingest tasks --
    "ingest-fng-daily": {
        "task": "api.tasks.ingest_fng",
        "schedule": crontab(hour=1, minute=0),  # 01:00 daily
        "options": {"queue": "ingest"},
    },
    "ingest-wikipedia-daily": {
        "task": "api.tasks.ingest_wikipedia",
        "schedule": crontab(hour=1, minute=15),  # 01:15 daily
        "options": {"queue": "ingest"},
    },
    "ingest-rss-crypto-daily": {
        "task": "api.tasks.ingest_rss_crypto",
        "schedule": crontab(hour=1, minute=30),  # 01:30 daily
        "options": {"queue": "ingest"},
    },
    "ingest-onchain-daily": {
        "task": "api.tasks.ingest_onchain",
        "schedule": crontab(hour=0, minute=40),  # 00:40 daily
        "options": {"queue": "ingest"},
    },
    # -- Compute tasks --
    "build-dataset-daily": {
        "task": "api.tasks.compute_build_dataset",
        "schedule": crontab(hour=2, minute=0),  # 02:00 daily
        "options": {"queue": "compute"},
    },
    "correlation-engine-daily": {
        "task": "api.tasks.compute_correlation",
        "schedule": crontab(hour=2, minute=30),  # 02:30 daily
        "options": {"queue": "compute"},
    },
    # -- Maintenance --
    "catchup-check-daily": {
        "task": "api.tasks.compute_catchup_check",
        "schedule": crontab(hour=3, minute=0),  # 03:00 daily
        "options": {"queue": "compute"},
    },
    "data-freshness-daily": {
        "task": "api.tasks.compute_data_freshness",
        "schedule": crontab(hour=3, minute=30),  # 03:30 daily
        "options": {"queue": "compute"},
    },
    # -- Alert evaluation --
    "evaluate-alerts-daily": {
        "task": "api.tasks.evaluate_alerts",
        "schedule": crontab(hour=3, minute=15),  # 03:15 daily
        "options": {"queue": "alerts"},
    },
}
