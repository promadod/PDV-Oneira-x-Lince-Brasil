from django.apps import AppConfig


class AppPdvConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_pdv'

    def ready(self):
        import app_pdv.signals  # noqa: F401
        import app_pdv.fiscal.models  # noqa: F401
