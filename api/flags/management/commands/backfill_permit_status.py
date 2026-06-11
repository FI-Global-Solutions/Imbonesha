from django.core.management.base import BaseCommand
from django.db import transaction

from flags.models import Flag, compute_severity
from parcels.models import Parcel, Permit


class Command(BaseCommand):
    help = "Recompute permit_status, severity, and severity_reason on all existing flags."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the DB.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        flags = Flag.objects.select_related("detection__job").all()
        total = flags.count()
        self.stdout.write(f"Processing {total} flags...")

        updated = 0
        skipped = 0
        counters: dict[str, int] = {}

        with transaction.atomic():
            for flag in flags.iterator(chunk_size=200):
                detection = flag.detection
                parcel_upi = detection.parcel_id  # FK to parcels_parcel.upi

                if not parcel_upi:
                    parcel = None
                else:
                    parcel = Parcel.objects.filter(upi=parcel_upi).first()

                if parcel is None:
                    severity, permit_status, reason = compute_severity(
                        has_active_permit=False,
                        permit_status=None,
                        permit_category=None,
                        detected_change_type=detection.change_type,
                        area_sqm=detection.area_sqm,
                        matched_parcel=False,
                    )
                else:
                    permits = Permit.objects.filter(parcel_id=parcel_upi).order_by("-issued_date")
                    most_recent = permits.first()
                    has_active = most_recent.status == "active" if most_recent else False
                    raw_status = most_recent.status if most_recent else None
                    permit_no = most_recent.permit_no if most_recent else None
                    permit_category = most_recent.category if most_recent else None

                    severity, permit_status, reason = compute_severity(
                        has_active_permit=has_active,
                        permit_status=raw_status,
                        permit_category=permit_category,
                        permit_no=permit_no,
                        detected_change_type=detection.change_type,
                        area_sqm=detection.area_sqm,
                        zone_type=parcel.zone_type,
                        matched_parcel=True,
                    )

                counters[permit_status] = counters.get(permit_status, 0) + 1

                changed = (
                    flag.permit_status != permit_status
                    or flag.severity != severity
                    or flag.severity_reason != reason
                )

                if not changed:
                    skipped += 1
                    continue

                if not dry_run:
                    flag.permit_status = permit_status
                    flag.severity = severity
                    flag.severity_reason = reason
                    flag.save(update_fields=["permit_status", "severity", "severity_reason"])

                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] Would update' if dry_run else 'Updated'} {updated} flags, "
            f"{skipped} already correct."
        ))
        self.stdout.write("Distribution:")
        for status, count in sorted(counters.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {status}: {count}")
