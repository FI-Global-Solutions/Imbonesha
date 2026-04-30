"""Core app — shared utilities, base models, management commands."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from django.contrib import admin
        admin.site.site_header = "Imbonesha — Government Administration"
        admin.site.site_title = "Imbonesha"
        admin.site.index_title = "System Administration"
