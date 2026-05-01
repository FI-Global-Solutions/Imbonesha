"""Backfill parcel matches for detections that have no parcel assigned.

Runs the same spatial join logic as the detection pipeline (boundary__intersects
+ largest overlap area) against all existing Detection rows where parcel is null.
Also updates the parent Flag's district field, which is denormalised from the parcel.

This command is safe to run multiple times — it only touches rows where
Detection.parcel is currently null.

Usage:
    python manage.py reattach_orphan_flags
    python manage.py reattach_orphan_flags --dry-run   # report counts, no writes
"""

from __future__ import annotations

import logging

from django.contrib.gis.db.models.functions import Area, Intersection
from django.core.management.base import BaseCommand
from django.db import transaction

from detections.models import Detection
from parcels.models import Parcel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-run spatial join for orphan detections (parcel=null) and backfill parcel + district."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]

        orphans = Detection.objects.filter(parcel__isnull=True).select_related("flag")
        total = orphans.count()

        self.stdout.write(f"Found {total} orphan detections (parcel=null)")
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        matched = 0
        still_unmatched = 0
        multi_parcel = 0

        for detection in orphans.iterator():
            candidates = (
                Parcel.objects.filter(boundary__intersects=detection.footprint)
                .annotate(overlap_area=Area(Intersection("boundary", detection.footprint)))
                .order_by("-overlap_area")
            )

            count = candidates.count()
            if count == 0:
                still_unmatched += 1
                logger.debug(
                    "Detection #%d: no parcel intersects footprint %s",
                    detection.pk,
                    detection.footprint.centroid,
                )
                continue

            if count > 1:
                multi_parcel += 1
                logger.debug(
                    "Detection #%d: %d parcels intersect — picking largest overlap",
                    detection.pk,
                    count,
                )

            best_parcel = candidates.first()
            matched += 1

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] Detection #{detection.pk} → parcel {best_parcel.upi} "
                    f"(district={best_parcel.district})"
                )
                continue

            with transaction.atomic():
                detection.parcel = best_parcel
                detection.save(update_fields=["parcel"])

                # Also backfill the denormalised district on the Flag.
                if hasattr(detection, "flag"):
                    flag = detection.flag
                    flag.district = best_parcel.district
                    flag.save(update_fields=["district"])

        self.stdout.write(
            f"\nResults:"
            f"\n  Matched:         {matched}"
            f"\n  Still unmatched: {still_unmatched}"
            f"\n  Multi-parcel:    {multi_parcel}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. {matched} detections reattached."))
