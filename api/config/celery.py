"""Celery configuration for Imbonesha.

Tasks live in their respective Django apps. This file just bootstraps
Celery and discovers them.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("imbonesha")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self) -> None:
    print(f"Request: {self.request!r}")
