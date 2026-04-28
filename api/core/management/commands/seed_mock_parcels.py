"""Seed mock parcels in the main API database.

In the next session, when we build the parcels Django app, this command
will mirror the parcel data from the permit-mock service into the main
database (via the PermitVerificationService adapter) so spatial joins
during detection can run locally without an external HTTP call.

For now it's a no-op placeholder so the Makefile doesn't break.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed mock parcels in the main API database."

    def handle(self, *args, **options) -> None:
        self.stdout.write(
            "seed_mock_parcels: no-op for now. Will be implemented when the "
            "parcels app is added in the next session."
        )
