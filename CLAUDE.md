# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AvoClassifier** is a Django REST API backend for an avocado disease classification system. It provides:
- User authentication (JWT-based) with email as the primary identifier
- Image upload and classification endpoints powered by a CNN model (Keras 3.x)
- Full **administrative API** for user management, permissions, and maintenance
- Enhanced Django Admin panel with bulk actions and visual indicators
- Integration with a trained Keras 3.x model for avocado disease classification

## Setup & Dependencies

### Installation

The project uses Django 6.0.5 with a Python virtual environment.

```bash
# Activate virtual environment
.venv\Scripts\activate             # Windows
source .venv/bin/activate          # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Apply migrations (includes token_blacklist and disease category updates)
# A default superuser is auto-created after migrate if none exists yet — see
# "Default Admin Auto-Creation" below. No manual createsuperuser step needed.
python manage.py migrate

# (Optional) create an additional/different superuser manually
python manage.py createsuperuser

# Start development server
python manage.py runserver
# Server: http://127.0.0.1:8000/ | Admin: http://127.0.0.1:8000/admin/
```

### Python 3.14 / TensorFlow Compatibility Note

TensorFlow/Keras are fully installed and the real model is active (`backend: keras`).
If TF becomes unavailable (e.g. after switching to Python 3.14), the AI service falls
back automatically to a **color-heuristic mode**. No code changes needed — the service
detects the backend on startup.

## Development Commands

```bash
python manage.py runserver [port]         # Start dev server
python manage.py makemigrations           # Generate migrations after model changes
python manage.py migrate                  # Apply migrations
python manage.py check                    # Check project integrity
python manage.py shell                    # Django interactive shell
python manage.py dbshell                  # SQLite prompt

# Tests (no tests exist yet)
python manage.py test                     # All tests
python manage.py test users               # App-specific tests
python manage.py test classifications
python manage.py test --verbosity=2       # Verbose output
```

## Architecture

### Three-Layer Structure

1. **API Layer** (`users/views.py`, `classifications/views.py`) — REST endpoints using DRF generics, request/response serialization, permission enforcement. Both user-facing and admin-only views.
2. **Business Logic Layer** (`classifications/services.py`, `classifications/ai_service.py`) — `run_classification()` orchestrates the workflow; `AvocadoClassifierService` wraps the ML model as a singleton with automatic fallback.
3. **Data Layer** (`users/models.py`, `classifications/models.py`) — Custom User model with email-based auth; Classification model tracking status lifecycle, image storage, and ML results.

### Classification Request Flow

```
POST /api/classifications/ (upload image)
  ↓
ClassificationCreateView.create()
  ↓
run_classification() [services.py]
  ├─ Update status: pending → processing
  ├─ classifier.predict(image_path) [ai_service.py]
  │  ├─ _preprocess(image_path)
  │  │    PIL open → RGB → resize 299×299 → float32/255 → batch dim
  │  ├─ _run_inference(tensor)
  │  │    ┌─ Keras available → model.predict() → softmax scores
  │  │    └─ Keras unavailable → _heuristic_scores() → color analysis
  │  └─ Return ClassificationResult (predicted_category, confidence, raw_scores)
  ├─ Save: predicted_category, confidence, raw_scores
  ├─ Update status: processing → completed (or failed)
  └─ Return Classification record

GET /api/classifications/<id>/   ← clients poll this for status updates
```

### AI Service Modes

| Backend | Condition | Behavior |
|---------|-----------|----------|
| `keras` | TensorFlow installed & compatible | Real CNN inference (299×299 input, softmax output) |
| `heuristic` | TF unavailable (Python 3.14) | Color-channel statistics analysis — partially functional |
| `none` | `load()` not called | Raises `RuntimeError` |

Check current mode via `GET /api/classifications/admin/stats/` → `model` field.

### Authentication Flow

```
POST /api/auth/register/       → creates User
POST /api/auth/login/          → returns access_token (30min) + refresh_token (7 days)
POST /api/auth/token/refresh/  → new access_token (old refresh invalidated via blacklist)
GET  /api/auth/profile/        → requires Bearer token
```

### Default Admin Auto-Creation

`users/signals.py` (`create_default_admin`) hooks Django's `post_migrate` signal (wired
in `users/apps.py`'s `ready()`) so a superuser is created automatically the moment
`migrate` finishes — no manual `createsuperuser` step required. It's idempotent: it
no-ops if any superuser already exists, and it's skipped entirely under `manage.py test`.

- **Dev environment** (`DEBUG=True`): if `DJANGO_SUPERUSER_EMAIL`/`DJANGO_SUPERUSER_PASSWORD`
  aren't set, falls back to `admin@avoclassifier.local` / `admin12345`.
- **Render/Fly (production, `DEBUG=False`)**: only creates the admin if both
  `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD` are set (Render: set as
  `sync: false` env vars in the dashboard, declared in `render.yaml`; Fly: `fly secrets
  set DJANGO_SUPERUSER_EMAIL=... DJANGO_SUPERUSER_PASSWORD=...`). If unset, no admin is
  created and nothing fails.

## Key Files

| File | Purpose |
|------|---------|
| `core/settings.py` | Django config: apps, middleware, DB, JWT settings, CORS, `AI_MODEL_DIR` |
| `core/urls.py` | Root URL router; mounts `/api/auth/` and `/api/classifications/` |
| `users/models.py` | Custom User model (email PK, name fields, timestamps) |
| `users/permissions.py` | `IsAdminOrStaff` — gates all `/admin/` API endpoints |
| `users/serializers.py` | `RegisterSerializer`, `UserSerializer`, `AdminUserSerializer`, `AdminCreateUserSerializer` |
| `users/views.py` | Auth + 4 admin views for user management |
| `users/admin.py` | Enhanced Django admin with bulk actions, computed columns, active badge |
| `classifications/models.py` | Classification & DiseaseCategory (saludable/antracnosis/pudricion); status enum |
| `classifications/services.py` | `run_classification()`: orchestrates full prediction workflow |
| `classifications/ai_service.py` | `AvocadoClassifierService` singleton: Keras inference + color-heuristic fallback |
| `classifications/views.py` | User views + 4 admin views (list, detail, stats, model reload) |
| `classifications/serializers.py` | Result + `AdminClassificationSerializer` |
| `classifications/admin.py` | Enhanced Django admin with color-coded status, confidence, image preview |
| `models/` | AI model files: `config.json`, `model.weights.h5`, `metadata.json` |

## URL Patterns

### Public / User Endpoints
```
/admin/                                  → Django admin panel
/api/auth/register/                      → POST user registration
/api/auth/login/                         → POST get JWT tokens
/api/auth/token/refresh/                 → POST refresh access token
/api/auth/profile/                       → GET/PATCH user profile
/api/classifications/                    → POST upload & classify | GET paginated list
/api/classifications/<id>/               → GET classification result (polling)
/api/classifications/history/            → GET user's classification history
```

### Admin-Only Endpoints (require is_staff or is_superuser)
```
# User management
/api/auth/admin/users/                   → GET list | POST create user
/api/auth/admin/users/<id>/              → GET | PATCH | DELETE user
/api/auth/admin/users/<id>/toggle-active/ → POST toggle is_active
/api/auth/admin/users/<id>/change-password/ → POST reset user password

# Classification management
/api/classifications/admin/all/          → GET all classifications (with filters)
/api/classifications/admin/all/<id>/     → GET | DELETE classification
/api/classifications/admin/stats/        → GET dashboard statistics
/api/classifications/admin/model/reload/ → POST reload AI model from disk
```

### Admin Query Parameters

| Endpoint | Params |
|----------|--------|
| `GET /api/auth/admin/users/` | `?search=email`, `?active=true\|false`, `?staff=true\|false` |
| `GET /api/classifications/admin/all/` | `?status=completed\|pending\|failed`, `?category=saludable\|antracnosis\|pudricion`, `?user_id=<int>`, `?search=email` |

## Disease Categories

| Value | Label | Description |
|-------|-------|-------------|
| `saludable` | Saludable | Healthy avocado, no disease detected |
| `antracnosis` | Antracnosis | Dark/brown spots caused by *Colletotrichum* fungus |
| `pudricion` | Pudrición Radicular | Root rot caused by *Phytophthora*/*Pythium* |

## AI Model Details

- **Architecture**: InceptionV3 fine-tuned — Keras Functional API (7 layers output)
- **Input**: `(None, 299, 299, 3)` — RGB images normalized to [0, 1]
- **Output**: 3 classes, softmax activation
- **Format**: Keras 3.14.0 directory format (`config.json` + `metadata.json` + `model.weights.h5`)
- **Location**: `models/InceptionV3_ft_best.keras/` — subdirectorio dentro de `AI_MODEL_DIR`
- **Status**: Cargado automáticamente al iniciar (`backend: keras`)

### Carga del modelo

El modelo está integrado y activo. `ClassificationsConfig.ready()` llama a `classifier.load()` al iniciar Django.
`_resolve_model_dir` escanea `AI_MODEL_DIR` buscando un subdirectorio `*.keras`; lo carga con
`keras.saving.deserialize_keras_object` + `model.load_weights` (necesario en Windows, donde
`keras.saving.load_model` falla al tratar un directorio `.keras` como archivo zip).

Para hot-reload del modelo sin reiniciar: `POST /api/classifications/admin/model/reload/`

## Django Admin Panel

Access at `/admin/` with a superuser account.

### User Admin Features
- **Columns**: email, first/last name, active badge (✓/✗), staff, superuser, classification count, created date
- **Search**: email, first name, last name
- **Filters**: is_staff, is_active, is_superuser
- **Bulk actions**: activate/deactivate users, grant/revoke staff permissions

### Classification Admin Features
- **Columns**: ID, user link, color-coded status badge, category, confidence (color-coded %), created/classified dates
- **Detail view**: image thumbnail preview, collapsible raw_scores and error sections
- **Bulk actions**: reprocess failed classifications, delete all failed
- **Date hierarchy** for time-based browsing

## Configuration Notes

- **Secret Key** (`core/settings.py`): Hardcoded — move to environment variable for production (`os.environ.get('SECRET_KEY')`).
- **Database**: SQLite in development (`db.sqlite3`); change `DATABASES` in settings.py for PostgreSQL.
- **CORS**: All origins allowed (`CORS_ALLOW_ALL_ORIGINS = True`) — restrict to frontend domain for production.
- **Media Storage**: Images saved to `media/classifications/YYYY/MM/DD/`.
- **Default Permissions**: All endpoints require `IsAuthenticated` except register/login; admin endpoints require `IsAdminOrStaff`.
- **JWT Blacklist**: `rest_framework_simplejwt.token_blacklist` is enabled — refresh tokens are invalidated on rotation.
- **AI_MODEL_DIR**: Points to `BASE_DIR / 'models'` — override in production to point to a different model directory.

## Future Improvements

### Async Processing (Celery)
`run_classification()` currently blocks the HTTP request. For production:
- Return 202 Accepted immediately after image upload
- Move classification logic to a Celery task
- Client polls `GET /api/classifications/<id>/` for status updates (infrastructure already exists)

### Production Hardening
- Move `SECRET_KEY` to env vars
- Restrict `CORS_ALLOW_ALL_ORIGINS` to specific domains
- Switch from SQLite to PostgreSQL
- Add pagination to admin list endpoints (currently no page limit)
- Add rate limiting on classification endpoint
