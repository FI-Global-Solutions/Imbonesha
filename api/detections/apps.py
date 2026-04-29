"""Detections app — detection jobs and individual detections."""

from django.apps import AppConfig


class DetectionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "detections"
