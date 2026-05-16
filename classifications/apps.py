import os

from django.apps import AppConfig


class ClassificationsConfig(AppConfig):
    name = "classifications"

    def ready(self):
        # En producción con poca RAM (ej. Render free tier 512 MB), carga diferida:
        # el modelo se carga en la primera petición en lugar de al iniciar.
        # En desarrollo o planes con RAM suficiente, carga inmediata al arrancar.
        if os.environ.get("LAZY_MODEL_LOAD", "False") != "True":
            from .ai_service import classifier
            classifier.load()
