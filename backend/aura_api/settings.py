
"""Django settings for a loopback-first local AURA installation."""

import os
import secrets

from django.core.exceptions import ImproperlyConfigured

from .config import (
    APP_NAME as AURA_APP_NAME,
    DATA_DIR,
    FRONTEND_ORIGIN,
    MEDIA_DIR,
    OUTPUT_DIR,
)


# ---------------------------------------------------------------------
# Core settings
# ---------------------------------------------------------------------

DEBUG = os.getenv("AURA_ENV", "development") != "production"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be configured when AURA_ENV=production."
        )

    SECRET_KEY = secrets.token_urlsafe(48)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "AURA_ALLOWED_HOSTS",
        "127.0.0.1,localhost,[::1]",
    ).split(",")
    if host.strip()
]

ROOT_URLCONF = "aura_api.urls"
WSGI_APPLICATION = "aura_api.wsgi.application"


# ---------------------------------------------------------------------
# Installed applications
# ---------------------------------------------------------------------

INSTALLED_APPS = [
    # Django built-in applications
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party applications
    "corsheaders",

    # AURA application
    "aura_api",
]


# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # AURA-specific middleware
    "aura_api.middleware.RequestIdMiddleware",
]


# ---------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------

database_engine = os.getenv("AURA_DB_ENGINE", "sqlite").lower()

if database_engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["AURA_DB_NAME"],
            "USER": os.environ["AURA_DB_USER"],
            "PASSWORD": os.environ["AURA_DB_PASSWORD"],
            "HOST": os.environ.get("AURA_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("AURA_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }

elif database_engine == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv(
                "AURA_DATABASE_PATH",
                str(DATA_DIR / "aura.db"),
            ),
            "OPTIONS": {
                "timeout": 20,
            },
        }
    }

else:
    raise ImproperlyConfigured(
        "AURA_DB_ENGINE must be either 'sqlite' or 'postgresql'."
    )


# ---------------------------------------------------------------------
# Default model configuration
# ---------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------
# Internationalization and time zone
# ---------------------------------------------------------------------

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"


# ---------------------------------------------------------------------
# Static files and media
# ---------------------------------------------------------------------

STATIC_URL = "static/"

MEDIA_ROOT = str(MEDIA_DIR)
OUTPUT_ROOT = str(OUTPUT_DIR)


# ---------------------------------------------------------------------
# CORS and CSRF configuration
# ---------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = sorted(
    {
        FRONTEND_ORIGIN,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
)

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = sorted(
    {
        FRONTEND_ORIGIN,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
)


# ---------------------------------------------------------------------
# Application configuration
# ---------------------------------------------------------------------

APP_NAME = AURA_APP_NAME

DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------
# Session and cookie security
# ---------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG


# ---------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"


# ---------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": 12,
        },
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]
