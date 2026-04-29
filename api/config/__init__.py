"""Imbonesha API config package.

Importing celery_app here ensures the Celery app is loaded when Django
starts so the @shared_task decorator works in any app.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
