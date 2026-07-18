from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signals
        post_migrate.connect(signals.create_default_admin, sender=self)
