"""
Script de pruebas para AvoClassifier API desplegada en Render.

Uso:
    python test/test_api.py                          # modo interactivo (Render por defecto)
    python test/test_api.py --email X --password Y  # con credenciales
    python test/test_api.py --register               # registrar nuevo usuario de prueba

    # Contra el servidor local (python manage.py runserver):
    python test/test_api.py --base-url http://127.0.0.1:8000 --email X --password Y

Variables de entorno alternativas:
    AVO_EMAIL, AVO_PASSWORD, AVO_BASE_URL

Cubre el flujo completo que consume el frontend: health, registro, login,
perfil, clasificación async (202 + polling), historial, export CSV, stats
admin, refresh de token y casos negativos (401/400/credenciales inválidas).
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import requests

# ─── Configuración ────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("AVO_BASE_URL", "https://avoclassifier-api.onrender.com").rstrip("/")
TEST_IMAGE = Path(__file__).parent / "imgs" / "avotest.jpeg"

BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"


# ─── Helpers de salida ────────────────────────────────────────────────────────

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def info(msg):  print(f"  {CYAN}→{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}!{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


def check_response(resp, expected_status, label):
    if resp.status_code == expected_status:
        ok(f"{label} [{resp.status_code}]")
        return True
    fail(f"{label} — esperado {expected_status}, obtenido {resp.status_code}")
    try:
        print(f"    {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except Exception:
        print(f"    {resp.text[:300]}")
    return False


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_health():
    """Comprueba que el servidor responde (cold start en Render puede tardar ~30s)."""
    header("1. Health check")
    info(f"Conectando a {BASE_URL} …")
    for attempt in range(1, 5):
        try:
            info(f"Intento {attempt}/4 (Render cold start puede tomar ~90s) …")
            resp = requests.get(f"{BASE_URL}/api/auth/profile/", timeout=90)
            # 401 = servidor vivo pero sin token (esperado)
            if resp.status_code in (200, 401, 403):
                ok(f"Servidor responde [{resp.status_code}]")
                return True
            warn(f"Respuesta inesperada [{resp.status_code}], intento {attempt}/4")
        except requests.exceptions.ConnectionError:
            warn(f"Sin conexión, intento {attempt}/4 — reintentando en 15s …")
            time.sleep(15)
        except requests.exceptions.Timeout:
            warn(f"Timeout, intento {attempt}/4 — reintentando …")
            time.sleep(5)
    fail("No se pudo conectar al servidor")
    return False


def test_register(email, password, first_name="Test", last_name="User"):
    """Registra un nuevo usuario. Devuelve True si tuvo éxito o el usuario ya existe."""
    header("2. Registro de usuario")
    payload = {
        "email": email,
        "password": password,
        "password2": password,  # el serializer exige confirmación de contraseña
        "first_name": first_name,
        "last_name": last_name,
    }
    resp = requests.post(f"{BASE_URL}/api/auth/register/", json=payload, timeout=30)

    if resp.status_code == 201:
        ok(f"Usuario registrado: {email}")
        return True
    if resp.status_code == 400 and "email" in resp.text.lower():
        warn("El usuario ya existe — usando credenciales existentes")
        return True
    check_response(resp, 201, "Registro")
    return False


def test_login(email, password):
    """Inicia sesión y devuelve el access token."""
    header("3. Login")
    payload = {"email": email, "password": password}
    resp = requests.post(f"{BASE_URL}/api/auth/login/", json=payload, timeout=30)

    if not check_response(resp, 200, "Login"):
        return None

    data = resp.json()
    token = data.get("access_token") or data.get("access")
    if not token:
        fail(f"Token no encontrado en la respuesta: {list(data.keys())}")
        return None

    ok(f"Token obtenido (primeros 20 chars): {token[:20]}…")
    return token


def test_profile(token):
    """Obtiene el perfil del usuario autenticado."""
    header("4. Perfil de usuario")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/api/auth/profile/", headers=headers, timeout=30)

    if not check_response(resp, 200, "GET /api/auth/profile/"):
        return False

    data = resp.json()
    info(f"Email    : {data.get('email')}")
    info(f"Nombre   : {data.get('first_name')} {data.get('last_name')}")
    info(f"Staff    : {data.get('is_staff')}")
    return True


def test_classify(token):
    """Sube avotest.jpeg y encola la clasificación. Devuelve el ID de clasificación.

    La API es asíncrona: responde 202 Accepted con `status: pending` de inmediato
    y procesa la inferencia en segundo plano. El resultado se obtiene por polling
    (ver test_poll_result).
    """
    header("5. Clasificación de imagen (encolado async)")

    if not TEST_IMAGE.exists():
        fail(f"Imagen no encontrada: {TEST_IMAGE}")
        return None

    info(f"Imagen   : {TEST_IMAGE.name} ({TEST_IMAGE.stat().st_size / 1024:.1f} KB)")

    headers = {"Authorization": f"Bearer {token}"}
    with open(TEST_IMAGE, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/classifications/",
            headers=headers,
            files={"image": (TEST_IMAGE.name, f, "image/jpeg")},
            timeout=120,
        )

    # La API devuelve 202 Accepted (procesamiento async vía thread pool executor).
    if not check_response(resp, 202, "POST /api/classifications/"):
        return None

    data = resp.json()
    clf_id = data.get("id")
    info(f"ID          : {clf_id}")
    info(f"Status      : {data.get('status')} (se resolverá por polling)")
    return clf_id


def test_poll_result(token, clf_id, max_wait=60):
    """Hace polling hasta que el status sea 'completed' o 'failed'."""
    header("6. Polling de resultado")

    if clf_id is None:
        warn("Saltando — no hay ID de clasificación")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + max_wait

    while time.time() < deadline:
        resp = requests.get(f"{BASE_URL}/api/classifications/{clf_id}/", headers=headers, timeout=30)
        if resp.status_code != 200:
            fail(f"GET /api/classifications/{clf_id}/ → {resp.status_code}")
            return False

        data = resp.json()
        status = data.get("status")

        if status == "completed":
            ok(f"Completado — Categoría: {BOLD}{data.get('predicted_category_display')}{RESET}")
            info(f"Confianza: {data.get('confidence', 0) * 100:.2f}%")
            raw = data.get("raw_scores") or {}
            if raw:
                info("Raw scores finales:")
                for cat, score in sorted(raw.items(), key=lambda x: x[1], reverse=True):
                    bar = "█" * int(score * 30)
                    print(f"    {cat:<14} {score * 100:5.2f}%  {bar}")
            return True

        if status == "failed":
            fail(f"Clasificación fallida: {data.get('error_message')}")
            return False

        info(f"Status: {status} — esperando …")
        time.sleep(3)

    fail(f"Timeout esperando resultado después de {max_wait}s")
    return False


def test_history(token):
    """Obtiene el historial de clasificaciones del usuario."""
    header("7. Historial")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/api/classifications/history/", headers=headers, timeout=30)

    if not check_response(resp, 200, "GET /api/classifications/history/"):
        return False

    data = resp.json()
    results = data if isinstance(data, list) else data.get("results", [])
    info(f"Clasificaciones en historial: {len(results)}")
    return True


def test_export_csv(token):
    """Descarga el historial como CSV (endpoint que consume el botón 'Exportar' del frontend)."""
    header("8. Export CSV")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{BASE_URL}/api/classifications/history/export/", headers=headers, timeout=30
    )

    if not check_response(resp, 200, "GET /api/classifications/history/export/"):
        return False

    ctype = resp.headers.get("Content-Type", "")
    disp = resp.headers.get("Content-Disposition", "")
    if "text/csv" not in ctype:
        fail(f"Content-Type inesperado: {ctype!r} (se esperaba text/csv)")
        return False
    ok(f"Content-Type: {ctype}")
    if "clasificaciones.csv" in disp:
        ok(f"Content-Disposition: {disp}")
    else:
        warn(f"Content-Disposition sin nombre de archivo esperado: {disp!r}")

    lineas = resp.text.splitlines()
    info(f"Filas en el CSV (incluye cabecera): {len(lineas)}")
    if lineas:
        info(f"Cabecera: {lineas[0]}")
    return True


def test_admin_stats(token):
    """Comprueba el backend del modelo (sólo accesible para staff/admin)."""
    header("9. Stats del modelo (admin)")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/api/classifications/admin/stats/", headers=headers, timeout=30)

    if resp.status_code == 403:
        warn("Usuario sin permisos de staff — omitiendo stats admin")
        return None

    if not check_response(resp, 200, "GET /api/classifications/admin/stats/"):
        return False

    data = resp.json()
    model_info = data.get("model", {})
    backend = model_info.get("backend", "desconocido")

    if backend == "keras":
        ok(f"Backend del modelo: {GREEN}{BOLD}keras{RESET} (modelo real activo)")
    elif backend == "heuristic":
        fail(f"Backend del modelo: {RED}{BOLD}heuristic{RESET} — TF/Keras no disponible en Render")
        warn("Esto explica por qué los resultados difieren del notebook")
    else:
        warn(f"Backend del modelo: {backend}")

    info(f"Total clasificaciones : {data.get('total_classifications', '?')}")
    info(f"Total usuarios        : {data.get('total_users', '?')}")
    return True


def test_token_refresh(token):
    """Prueba el endpoint de refresh (requiere el refresh token, que no guardamos aquí)."""
    header("10. Token refresh (smoke test)")
    # Solo verificamos que el endpoint existe y rechaza un token inválido
    resp = requests.post(
        f"{BASE_URL}/api/auth/token/refresh/",
        json={"refresh": "invalid.token.here"},
        timeout=30,
    )
    if resp.status_code in (400, 401):
        ok(f"Endpoint /token/refresh/ existe y valida tokens [{resp.status_code}]")
        return True
    warn(f"Respuesta inesperada: {resp.status_code}")
    return False


# ─── Casos negativos (el frontend debe manejar estos errores con gracia) ──────

def test_login_invalid_credentials():
    """Login con credenciales incorrectas debe devolver 401 (no 500 ni 200)."""
    header("11. Login con credenciales inválidas")
    resp = requests.post(
        f"{BASE_URL}/api/auth/login/",
        json={"email": "no-existe@example.com", "password": "credencial-incorrecta"},
        timeout=30,
    )
    # SimpleJWT devuelve 401 para credenciales inválidas.
    if resp.status_code in (400, 401):
        ok(f"Credenciales inválidas rechazadas [{resp.status_code}]")
        return True
    fail(f"Se esperaba 401, se obtuvo {resp.status_code}")
    return False


def test_classify_without_token():
    """Clasificar sin token de autenticación debe devolver 401."""
    header("12. Clasificación sin autenticación")
    if not TEST_IMAGE.exists():
        warn(f"Imagen no encontrada: {TEST_IMAGE} — omitiendo")
        return None
    with open(TEST_IMAGE, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/classifications/",
            files={"image": (TEST_IMAGE.name, f, "image/jpeg")},
            timeout=60,
        )
    if resp.status_code == 401:
        ok("Petición sin token rechazada [401]")
        return True
    fail(f"Se esperaba 401, se obtuvo {resp.status_code}")
    return False


def test_classify_non_image(token):
    """Subir un archivo que no es imagen debe devolver 400 (validación de imagen)."""
    header("13. Clasificación con archivo no-imagen")
    headers = {"Authorization": f"Bearer {token}"}
    fake = ("fake.jpg", io.BytesIO(b"esto no es una imagen"), "image/jpeg")
    resp = requests.post(
        f"{BASE_URL}/api/classifications/",
        headers=headers,
        files={"image": fake},
        timeout=60,
    )
    if resp.status_code == 400:
        ok("Archivo no-imagen rechazado [400]")
        return True
    if resp.status_code == 429:
        warn("Rate limit alcanzado (429) — omitiendo validación de archivo")
        return None
    fail(f"Se esperaba 400, se obtuvo {resp.status_code}")
    return False


# ─── Punto de entrada ─────────────────────────────────────────────────────────

def main():
    global BASE_URL

    parser = argparse.ArgumentParser(description="Tests para AvoClassifier API")
    parser.add_argument("--email", default=os.environ.get("AVO_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("AVO_PASSWORD", ""))
    parser.add_argument("--register", action="store_true", help="Registrar usuario antes de login")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    BASE_URL = args.base_url.rstrip("/")

    print(f"\n{BOLD}AvoClassifier API — Test Suite{RESET}")
    print(f"Base URL : {BASE_URL}")
    print(f"Imagen   : {TEST_IMAGE}")
    print("─" * 50)

    # Credenciales
    email = args.email
    password = args.password

    if not email:
        email = input("\nEmail: ").strip()
    if not password:
        import getpass
        password = getpass.getpass("Password: ")

    # ── Ejecutar tests ────────────────────────────────────────────────────────
    results = {}

    results["health"] = test_health()
    if not results["health"]:
        print(f"\n{RED}Servidor no disponible. Abortando.{RESET}\n")
        sys.exit(1)

    if args.register:
        results["register"] = test_register(email, password)

    token = test_login(email, password)
    results["login"] = token is not None
    if not token:
        print(f"\n{RED}Login fallido. Abortando.{RESET}\n")
        sys.exit(1)

    results["profile"]  = test_profile(token)
    clf_id              = test_classify(token)
    results["classify"] = clf_id is not None
    results["poll"]     = test_poll_result(token, clf_id)
    results["history"]  = test_history(token)
    results["export"]   = test_export_csv(token)
    results["stats"]    = test_admin_stats(token)
    results["refresh"]  = test_token_refresh(token)

    # ── Casos negativos ───────────────────────────────────────────────────────
    results["login_invalido"]   = test_login_invalid_credentials()
    results["sin_token"]        = test_classify_without_token()
    results["archivo_no_imagen"] = test_classify_non_image(token)

    # ── Resumen ───────────────────────────────────────────────────────────────
    header("Resumen")
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)

    for name, result in results.items():
        if result is True:
            ok(name)
        elif result is False:
            fail(name)
        else:
            warn(f"{name} (omitido)")

    print(f"\n  {GREEN}{passed} ok{RESET}  {RED}{failed} fail{RESET}  {YELLOW}{skipped} omitido{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
