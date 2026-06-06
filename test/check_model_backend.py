"""
Script rápido para diagnosticar el backend del modelo en Render.
No requiere credenciales de usuario normal — usa superusuario.

Uso:
    python test/check_model_backend.py --email admin@x.com --password secret
"""

import argparse
import os
import sys

import requests

BASE_URL = os.environ.get("AVO_BASE_URL", "https://avoclassifier-api.onrender.com").rstrip("/")

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico del backend del modelo")
    parser.add_argument("--email", default=os.environ.get("AVO_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("AVO_PASSWORD", ""))
    args = parser.parse_args()

    email = args.email or input("Email admin: ").strip()
    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("Password: ")

    # Login
    print(f"\n{BOLD}Conectando a {BASE_URL}{RESET}")
    resp = requests.post(f"{BASE_URL}/api/auth/login/", json={"email": email, "password": password}, timeout=60)
    if resp.status_code != 200:
        print(f"{RED}Login fallido [{resp.status_code}]: {resp.text[:200]}{RESET}")
        sys.exit(1)

    data = resp.json()
    token = data.get("access_token") or data.get("access")
    headers = {"Authorization": f"Bearer {token}"}

    # Stats admin
    resp = requests.get(f"{BASE_URL}/api/classifications/admin/stats/", headers=headers, timeout=60)
    if resp.status_code == 403:
        print(f"{YELLOW}El usuario no tiene permisos de staff. Usa un superusuario.{RESET}")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"{RED}Stats fallido [{resp.status_code}]: {resp.text[:200]}{RESET}")
        sys.exit(1)

    stats = resp.json()
    model = stats.get("model", {})
    backend = model.get("backend", "?")

    print(f"\n{'─'*45}")
    print(f"  Backend   : ", end="")
    if backend == "keras":
        print(f"{GREEN}{BOLD}keras ✓{RESET}  (modelo real InceptionV3 activo)")
    elif backend == "heuristic":
        print(f"{RED}{BOLD}heuristic ✗{RESET}  (TF/Keras no disponible — resultados incorrectos)")
    else:
        print(f"{YELLOW}{backend}{RESET}")

    print(f"  Cargado   : {model.get('loaded')}")
    print(f"  Categorías: {model.get('categories')}")
    print(f"\n  Total clasificaciones : {stats.get('total_classifications', '?')}")
    print(f"  Total usuarios        : {stats.get('total_users', '?')}")

    dist = stats.get("category_distribution") or stats.get("distribution") or {}
    if dist:
        print(f"\n  Distribución por categoría:")
        for cat, count in dist.items():
            print(f"    {cat:<14}: {count}")

    print(f"{'─'*45}\n")

    if backend != "keras":
        print(f"{RED}PROBLEMA DETECTADO:{RESET} El backend no usa el modelo real.")
        print("  Posibles causas:")
        print("  1. TensorFlow no está en requirements.txt o falla al instalarse en Render")
        print("  2. El modelo .keras no está en el path correcto (AI_MODEL_DIR)")
        print("  3. La versión de Python en Render es incompatible con TF")
        print("\n  Revisa los logs de Render buscando:")
        print('    "Backend ML no disponible"')
        print('    "Error inesperado al cargar el modelo Keras"')
        sys.exit(1)


if __name__ == "__main__":
    main()
