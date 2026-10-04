from django.apps import AppConfig


class CoaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coa"

    def ready(self):
        from . import signals
