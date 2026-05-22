"""Base Django settings — shared across dev, staging, prod.

Environment-specific settings live in dev.py, staging.py, prod.py and
import from this base module.
"""

from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="dev-secret-not-for-production")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # GeoDjango
    # Third-party
    "rest_framework",
    "rest_framework_gis",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    # Imbonesha apps
    "core",
    "accounts",
    "parcels",
    "imagery",
    "detections",
    "flags",
    "notifications",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgis://imbonesha:imbonesha_dev@db:5432/imbonesha",
    ),
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache — used by the permit verification adapter to cut load on KUBAKA / mock.
# In production we'd use Redis directly here too. Locmem is fine for dev and
# for tests since each process gets its own cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env.str("REDIS_URL", default="redis://redis:6379/1"),
        "KEY_PREFIX": "imbonesha",
    },
}

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
}

# Celery
CELERY_BROKER_URL = env.str("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

# External services
PERMIT_SERVICE_URL = env.str("PERMIT_SERVICE_URL", default="http://permit-service:8001")
PERMIT_ADAPTER = env.str("PERMIT_ADAPTER", default="mock")  # "mock" or "kubaka"
ML_SERVICE_URL = env.str("ML_SERVICE_URL", default="http://ml-service:8002")

# SimpleJWT — use email as the login field (matches AUTH_USER_MODEL)
from datetime import timedelta

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# The default TokenObtainPairView uses USERNAME_FIELD automatically
# (accounts.User.USERNAME_FIELD = "email"), so no custom serializer needed.

# Notifications
NOTIFICATION_BACKEND = env.str("NOTIFICATION_BACKEND", default="console")
SENDGRID_API_KEY = env.str("SENDGRID_API_KEY", default="")
NOTIFICATION_FROM_EMAIL = env.str(
    "NOTIFICATION_FROM_EMAIL", default="notifications@imbonesha.gov.rw"
)
FRONTEND_URL = env.str("FRONTEND_URL", default="http://localhost:3000")

# MinIO / S3
MINIO_ENDPOINT = env.str("MINIO_ENDPOINT", default="minio:9000")
MINIO_ACCESS_KEY = env.str("MINIO_ACCESS_KEY", default="imbonesha")
MINIO_SECRET_KEY = env.str("MINIO_SECRET_KEY", default="imbonesha_dev")
MINIO_BUCKET = env.str("MINIO_BUCKET", default="imbonesha-imagery")
MINIO_SECURE = env.bool("MINIO_SECURE", default=False)
# Public-facing MinIO URL used to rewrite presigned URLs for browser access.
# In dev this is localhost:9007; in prod it would be the CDN/load balancer URL.
MINIO_PUBLIC_ENDPOINT = env.str("MINIO_PUBLIC_ENDPOINT", default="http://localhost:9007")
