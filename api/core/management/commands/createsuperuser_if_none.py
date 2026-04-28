"""Create a default superuser if no superuser exists.

Used during `make bootstrap` so developers don't have to interactively
answer prompts. Default credentials: admin@imbonesha.local / changeme.
Rotate before any non-local deployment.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a default superuser if none exists."

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Superuser already exists, skipping.")
            return

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@imbonesha.local")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "changeme")

        User.objects.create_superuser(
            username=email,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Superuser '{email}' created."))
        self.stdout.write(self.style.WARNING("Default password is 'changeme' — rotate it."))
