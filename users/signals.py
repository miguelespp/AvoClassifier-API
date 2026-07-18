import os
import sys

from django.conf import settings


def create_default_admin(sender, **kwargs):
    """Crea un superusuario por defecto tras `migrate`, si aún no existe ninguno.

    En producción (DEBUG=False) requiere DJANGO_SUPERUSER_EMAIL y
    DJANGO_SUPERUSER_PASSWORD; si no están definidas, no hace nada.
    En desarrollo (DEBUG=True) usa credenciales por defecto si esas
    variables no están definidas, para que el admin quede listo tras
    el primer `migrate` sin pasos manuales.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        return

    from .models import User

    if User.objects.filter(is_superuser=True).exists():
        return

    email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

    if not email or not password:
        if not settings.DEBUG:
            return
        email = email or "admin@avoclassifier.local"
        password = password or "admin12345"

    User.objects.create_superuser(email=email, password=password)
    print(f"[users] Superusuario por defecto creado: {email}")
