from django.apps import AppConfig


class GetdataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'getData'

    def ready(self):
        from .noon_scheduler import start_noon_flow_scheduler

        start_noon_flow_scheduler()
