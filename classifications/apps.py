from django.apps import AppConfig


class ClassificationsConfig(AppConfig):
    name = "classifications"

    def ready(self):
        # Precarga el modelo en memoria al iniciar Django.
        from .ai_service import classifier

        classifier.load()
