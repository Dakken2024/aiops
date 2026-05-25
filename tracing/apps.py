from django.apps import AppConfig


class TracingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracing'
    verbose_name = '链路追踪'
