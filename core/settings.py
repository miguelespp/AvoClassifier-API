import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Seguridad ────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-+-8!f+5a776u=j+9t=@!+qmwc11+y$f-4q-2+i=^x1%t9d+au^",
)

DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

# ── Aplicaciones ─────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local
    "users",
    "classifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

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

WSGI_APPLICATION = "core.wsgi.application"

# ── Base de datos ─────────────────────────────────────────────────────────────
# En Render: variable de entorno DATABASE_URL con la URL de PostgreSQL.
# En desarrollo: SQLite local.

_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    DATABASES = {
        "default": dj_database_url.config(
            default=_database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Validadores de contraseña ─────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internacionalización ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Archivos estáticos ────────────────────────────────────────────────────────

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Archivos de media (imágenes subidas) ──────────────────────────────────────
# Local (DEBUG / sin GCS): se sirven vía core/urls.py.
# Render con disco local: montar un disco persistente y apuntar MEDIA_ROOT ahí.

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media")))

# ── Backends de almacenamiento ────────────────────────────────────────────────
# Por defecto: filesystem local para media + WhiteNoise para estáticos.
# Si USE_GCS=true, las imágenes de clasificación se guardan en Firebase Storage
# (el bucket de Google Cloud Storage del proyecto Firebase) con URLs firmadas
# privadas — cada imagen sólo es accesible vía una signed URL temporal.

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if os.environ.get("USE_GCS") == "false":
    _gcs_options = {
        "bucket_name": os.environ["GS_BUCKET_NAME"],   # ej: avo-classifier.firebasestorage.app
        "project_id": os.environ.get("GS_PROJECT_ID"),
        "default_acl": None,            # objetos privados (uniform bucket-level access)
        "querystring_auth": True,       # image.url devuelve una signed URL
        "file_overwrite": False,        # nombres en colisión → sufijo único (no pisar archivos)
        "expiration": timedelta(
            seconds=int(os.environ.get("GS_EXPIRATION", "3600"))
        ),
    }

    # Credenciales de la service account (Firebase Console → Configuración →
    # Cuentas de servicio → Generar nueva clave privada). Dos formas:
    #   1. GS_CREDENTIALS_JSON  → el contenido JSON completo (cómodo en Render).
    #   2. GOOGLE_APPLICATION_CREDENTIALS → ruta a un archivo .json (dev local).
    # Si no se define ninguna, google-auth usa las credenciales por defecto.
    _gcs_creds_json = os.environ.get("GS_CREDENTIALS_JSON")
    if _gcs_creds_json:
        import json

        from google.oauth2 import service_account

        _gcs_options["credentials"] = service_account.Credentials.from_service_account_info(
            json.loads(_gcs_creds_json)
        )

    STORAGES["default"] = {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": _gcs_options,
    }

# ── Modelo de usuario ─────────────────────────────────────────────────────────

AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ─────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/hour",
        "user": "200/hour",
        "classification": "30/hour",
    },
}

# ── JWT ───────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── CORS ──────────────────────────────────────────────────────────────────────
# En producción: especifica los orígenes del frontend en CORS_ALLOWED_ORIGINS.
# Ejemplo: CORS_ALLOWED_ORIGINS=https://mi-app.com,https://app.mi-dominio.com

_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(",") if o.strip()]
else:
    CORS_ALLOW_ALL_ORIGINS = True  # Solo en desarrollo (DEBUG=True)

# ── Documentación API ─────────────────────────────────────────────────────────

SPECTACULAR_SETTINGS = {
    "TITLE": "AvoClassifier API",
    "DESCRIPTION": (
        "REST API para clasificación de enfermedades en aguacate mediante CNN.\n\n"
        "## Autenticación\n"
        "Usa JWT Bearer token. Obtén el token en `POST /api/auth/login/` "
        "e inclúyelo en el header: `Authorization: Bearer <token>`.\n\n"
        "## Roles\n"
        "- **Usuario**: endpoints de clasificación e historial propio.\n"
        "- **Admin/Staff**: endpoints `/admin/` con acceso completo."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SECURITY": [{"jwtAuth": []}],
    "TAGS": [
        {"name": "auth", "description": "Registro, login y gestión de perfil"},
        {"name": "classifications", "description": "Subir imágenes y consultar resultados"},
        {"name": "admin-users", "description": "Gestión de usuarios (solo admin)"},
        {"name": "admin-classifications", "description": "Gestión de clasificaciones (solo admin)"},
    ],
}

# ── Modelo de IA ──────────────────────────────────────────────────────────────
# En Render con disco persistente: AI_MODEL_DIR=/opt/render/project/src/models

AI_MODEL_DIR = Path(os.environ.get("AI_MODEL_DIR", str(BASE_DIR / "models")))
