
import os
from pathlib import Path

from dotenv import load_dotenv


# ==========================================================
# BASE CONFIGURATION
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("true", "1", "yes", "on")


def env_list(name, default=""):
    return [
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


def env_value(name, default=""):
    return os.getenv(name, default).strip()


# ==========================================================
# SECURITY CONFIGURATION
# ==========================================================

SECRET_KEY = env_value("SECRET_KEY")

if not SECRET_KEY or SECRET_KEY == "replace-this-with-a-unique-secret-key":
    raise ValueError(
        "Set a secure SECRET_KEY in your .env file."
    )

DEBUG = env_bool("DEBUG", True)

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "",
)

SECURE_SSL_REDIRECT = env_bool(
    "SECURE_SSL_REDIRECT",
    False,
)

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool(
        "SECURE_SSL_REDIRECT",
        True,
    )


# ==========================================================
# APPLICATION DEFINITIONS
# ==========================================================

INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",

    # Local applications
    "mpesa",
]


# ==========================================================
# MIDDLEWARE
# ==========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ==========================================================
# URL CONFIGURATION
# ==========================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# ==========================================================
# TEMPLATE CONFIGURATION
# ==========================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

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


# ==========================================================
# DATABASE CONFIGURATION
# SQLite and PostgreSQL support
# ==========================================================

DB_ENGINE = env_value("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "postgresql":

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",

            "NAME": env_value(
                "DB_NAME",
                "mpesa_gateway",
            ),

            "USER": env_value(
                "DB_USER",
                "postgres",
            ),

            "PASSWORD": env_value(
                "DB_PASSWORD",
            ),

            "HOST": env_value(
                "DB_HOST",
                "localhost",
            ),

            "PORT": env_value(
                "DB_PORT",
                "5432",
            ),

            "CONN_MAX_AGE": 60,

            "CONN_HEALTH_CHECKS": True,
        }
    }

elif DB_ENGINE == "sqlite":

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",

            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

else:

    raise ValueError(
        "Unsupported DB_ENGINE. "
        "Use sqlite or postgresql."
    )


# ==========================================================
# PASSWORD VALIDATION
# ==========================================================

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


# ==========================================================
# INTERNATIONALIZATION
# ==========================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = env_value(
    "TIME_ZONE",
    "Africa/Nairobi",
)

USE_I18N = True

USE_TZ = True


# ==========================================================
# STATIC AND MEDIA FILES
# ==========================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []

if (BASE_DIR / "static").exists():
    STATICFILES_DIRS.append(
        BASE_DIR / "static"
    )

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": (
            "django.core.files.storage.FileSystemStorage"
        ),
    },

    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },
}


# ==========================================================
# DJANGO REST FRAMEWORK
# ==========================================================

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi.AutoSchema"
    ),

    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],

    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),

    "PAGE_SIZE": 20,
}


# ==========================================================
# API DOCUMENTATION
# ==========================================================

SPECTACULAR_SETTINGS = {
    "TITLE": "Django M-PESA Gateway API",

    "DESCRIPTION": (
        "Reusable Safaricom Daraja payment gateway "
        "supporting STK Push, PayBill and future "
        "Buy Goods integrations."
    ),

    "VERSION": "1.0.0",

    "SERVE_INCLUDE_SCHEMA": False,
}


# ==========================================================
# CORS CONFIGURATION
# ==========================================================

CORS_ALLOW_ALL_ORIGINS = DEBUG

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "",
)


# ==========================================================
# SAFARICOM DARAJA CONFIGURATION
# ==========================================================

MPESA_ENVIRONMENT = env_value(
    "MPESA_ENVIRONMENT",
    "sandbox",
).lower()

if MPESA_ENVIRONMENT not in ("sandbox", "production"):
    raise ValueError(
        "MPESA_ENVIRONMENT must be sandbox or production."
    )

MPESA_CONSUMER_KEY = env_value(
    "MPESA_CONSUMER_KEY",
)

MPESA_CONSUMER_SECRET = env_value(
    "MPESA_CONSUMER_SECRET",
)

MPESA_SHORTCODE = env_value(
    "MPESA_SHORTCODE",
)

MPESA_PASSKEY = env_value(
    "MPESA_PASSKEY",
)

MPESA_TILL_NUMBER = env_value(
    "MPESA_TILL_NUMBER",
)

MPESA_CALLBACK_URL = env_value(
    "MPESA_CALLBACK_URL",
)

MPESA_ACCOUNT_REFERENCE = env_value(
    "MPESA_ACCOUNT_REFERENCE",
    "HPDS",
)

MPESA_TRANSACTION_DESC = env_value(
    "MPESA_TRANSACTION_DESC",
    "Payment",
)

MPESA_API_KEY = env_value(
    "MPESA_API_KEY",
)


# ==========================================================
# EMAIL CONFIGURATION
# ==========================================================

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
)

DEFAULT_FROM_EMAIL = env_value(
    "DEFAULT_FROM_EMAIL",
    "payments@example.com",
)


# ==========================================================
# LOGGING
# ==========================================================

LOGGING = {
    "version": 1,

    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{levelname} {asctime} "
                "{name} {message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "loggers": {
        "mpesa": {
            "handlers": ["console"],
            "level": env_value(
                "LOG_LEVEL",
                "INFO",
            ),
            "propagate": False,
        },
    },
}


# ==========================================================
# DEFAULT PRIMARY KEY
# ==========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
