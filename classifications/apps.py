from django.apps import AppConfig


class ClassificationsConfig(AppConfig):
    name = 'classifications'

    def ready(self):
        # Precarga el modelo en memoria al iniciar Django.
        # Cuando _load_model() esté implementado, descomenta la línea de abajo.
        # from .ai_service import classifier
        # classifier.load()
        pass
