"""Flags app — flag lifecycle, inspections, and audit log."""

from django.apps import AppConfig


class FlagsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flags"

    def ready(self) -> None:
        # Register signal handlers declared in flags.signals.
        import flags.signals  # noqa: F401
