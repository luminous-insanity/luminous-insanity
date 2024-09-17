from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.dispatch import receiver

class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        from . import jobs
        post_migrate.connect(start_scheduler, sender=self)

def start_scheduler(sender, **kwargs):
    from .jobs import start
    start()
