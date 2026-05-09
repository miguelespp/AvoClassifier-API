# AvoClassifier — API de Clasificación de Enfermedades en Aguacate

API REST backend para clasificar enfermedades en imágenes de aguacate mediante un modelo de IA. Construida con Django REST Framework y autenticación JWT.

## Stack

- **Python 3.14** / **Django 6.0.5**
- **Django REST Framework** — endpoints REST
- **SimpleJWT** — autenticación con tokens JWT
- **django-cors-headers** — CORS para el frontend
- **Pillow** — procesamiento de imágenes
- **SQLite** (desarrollo) — intercambiable por PostgreSQL

## Instalación

```bash
# 1. Activar entorno virtual
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Aplicar migraciones
python manage.py migrate

# 4. Crear superusuario (acceso al admin)
python manage.py createsuperuser

# 5. Levantar servidor
python manage.py runserver
```

Servidor disponible en `http://127.0.0.1:8000/` | Admin en `http://127.0.0.1:8000/admin/`

## Endpoints

Todos los endpoints protegidos requieren el header:
```
Authorization: Bearer <access_token>
```

### Autenticación

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| `POST` | `/api/auth/register/` | Registrar usuario | No |
| `POST` | `/api/auth/login/` | Obtener tokens JWT | No |
| `POST` | `/api/auth/token/refresh/` | Renovar access token | No |
| `GET` | `/api/auth/profile/` | Ver perfil | Si |
| `PATCH` | `/api/auth/profile/` | Editar perfil | Si |

**Registro**
```json
POST /api/auth/register/
{
  "email": "usuario@ejemplo.com",
  "password": "contraseña123",
  "first_name": "Juan",
  "last_name": "Pérez"
}
```

**Login** — devuelve `access` (30 min) y `refresh` (7 días):
```json
POST /api/auth/login/
{
  "email": "usuario@ejemplo.com",
  "password": "contraseña123"
}
```

### Clasificaciones

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/classifications/` | Subir imagen y clasificar |
| `GET` | `/api/classifications/<id>/` | Consultar resultado (polling) |
| `GET` | `/api/classifications/history/` | Historial del usuario |

**Subir imagen para clasificar** (multipart/form-data):
```
POST /api/classifications/
Content-Type: multipart/form-data

image: <archivo_imagen>
```

**Respuesta:**
```json
{
  "id": 1,
  "image": "media/classifications/2026/05/08/foto.jpg",
  "status": "completed",
  "predicted_category": "category_a",
  "predicted_category_display": "Categoría A",
  "confidence": 0.94,
  "raw_scores": {"category_a": 0.94, "category_b": 0.04, "category_c": 0.02},
  "error_message": "",
  "created_at": "2026-05-08T12:00:00Z",
  "classified_at": "2026-05-08T12:00:01Z"
}
```

El campo `status` puede ser: `pending` → `processing` → `completed` / `failed`.

## Estructura del proyecto

```
tsm_pr/
├── core/               # Configuración Django (settings, urls, wsgi)
├── users/              # App de usuarios con email como PK
│   ├── models.py       # Modelo User personalizado
│   ├── serializers.py
│   ├── views.py        # Register, Login, Profile
│   └── urls.py
├── classifications/    # App de clasificación de imágenes
│   ├── models.py       # Classification + DiseaseCategory + estados
│   ├── ai_service.py   # AvocadoClassifierService (stubs del modelo IA)
│   ├── services.py     # run_classification() — orquesta el flujo
│   ├── views.py        # Create, Detail, List
│   └── urls.py
├── media/              # Imágenes subidas (generado automáticamente)
├── manage.py
└── db.sqlite3
```

## Estado actual

La estructura de la API está completa. La integración del modelo de IA está **pendiente**: `classifications/ai_service.py` contiene los stubs `_load_model()`, `_preprocess()` y `_run_inference()` listos para implementar cuando los pesos del modelo estén disponibles.

Mientras tanto, `POST /api/classifications/` responde con `status: failed` y el error de `NotImplementedError`.

## Configuración para producción

Antes de desplegar, actualizar en `core/settings.py`:

- `SECRET_KEY` → usar variable de entorno
- `DEBUG = False`
- `ALLOWED_HOSTS` → dominio del servidor
- `CORS_ALLOW_ALL_ORIGINS = False` → especificar el dominio del frontend
- `DATABASES` → cambiar a PostgreSQL
- `AI_MODEL_PATH` → descomentar y apuntar al archivo `.pth` del modelo
