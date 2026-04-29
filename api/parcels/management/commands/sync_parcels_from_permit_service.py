"""Sync parcels and permits from the source registry into the local mirror.

Iterates the seeded UPI grid (1/01/03/05/0001 through 1/01/03/05/0080),
fetches each one from the permit service, and upserts it locally.

In production this command:
- Runs nightly via Celery beat
- Pages through all UPIs in the registry, not just our demo grid
- Uses ETag / Last-Modified headers for conditional fetches
- Reports drift (UPIs in local mirror but not in registry, etc.)

For now we keep it simple. Run with:

    docker compose -f infra/docker-compose.yml exec api \\
        python manage.py sync_parcels_from_permit_service
"""

from datetime import datetime

import httpx
from django.contrib.gis.geos import GEOSGeometry, Point, Polygon
from django.core.management.base import BaseCommand
from django.db import transaction

from parcels.models import Parcel, Permit


class Command(BaseCommand):
    help = "Sync parcels and permits from the configured permit registry."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--service-url",
            default=None,
            help="Override PERMIT_SERVICE_URL setting (useful for testing).",
        )
        parser.add_argument(
            "--upi-pattern",
            default="1/01/03/05/{n:04d}",
            help="Format string for UPI generation. {n} is the parcel index.",
        )
        parser.add_argument(
            "--start", type=int, default=1, help="First parcel index (inclusive)."
        )
        parser.add_argument(
            "--end", type=int, default=80, help="Last parcel index (inclusive)."
        )

    def handle(self, *args, **options) -> None:
        from django.conf import settings

        service_url = options["service_url"] or settings.PERMIT_SERVICE_URL
        pattern = options["upi_pattern"]
        start = options["start"]
        end = options["end"]

        self.stdout.write(f"Syncing parcels from {service_url}")
        self.stdout.write(f"UPI range: {pattern.format(n=start)} → {pattern.format(n=end)}")

        synced = 0
        skipped = 0
        permits_total = 0
        errors: list[tuple[str, str]] = []

        # We use a single HTTP client to reuse connections, but we don't put
        # the whole sync in one transaction — partial progress is fine if a
        # later parcel fails.
        with httpx.Client(base_url=service_url, timeout=10.0) as client:
            for n in range(start, end + 1):
                upi = pattern.format(n=n)
                try:
                    response = client.get(f"/api/v1/parcels/{upi}")
                    if response.status_code == 404:
                        skipped += 1
                        continue
                    response.raise_for_status()
                    payload = response.json()
                except httpx.HTTPError as exc:
                    errors.append((upi, str(exc)))
                    continue

                with transaction.atomic():
                    permits_count = self._upsert_parcel(payload)
                    synced += 1
                    permits_total += permits_count

                if synced % 20 == 0:
                    self.stdout.write(f"  ...{synced} parcels synced")

        self.stdout.write(self.style.SUCCESS(f"Synced {synced} parcels with {permits_total} permits"))
        if skipped:
            self.stdout.write(f"Skipped (404): {skipped}")
        if errors:
            self.stdout.write(self.style.WARNING(f"Errors: {len(errors)}"))
            for upi, msg in errors[:10]:
                self.stdout.write(f"  {upi}: {msg}")

    def _upsert_parcel(self, payload: dict) -> int:
        """Upsert a parcel and replace all its permits. Returns permit count."""
        # GeoJSON polygon → GEOS Polygon. The mock returns
        # {"type": "Polygon", "coordinates": [[[lng, lat], ...]]}.
        boundary = GEOSGeometry(_geojson_dumps(payload["boundary_geojson"]), srid=4326)
        centroid = Point(payload["centroid_lng"], payload["centroid_lat"], srid=4326)

        parcel, _ = Parcel.objects.update_or_create(
            upi=payload["upi"],
            defaults={
                "boundary": boundary,
                "centroid": centroid,
                "owner_name": payload["owner_name"],
                "land_use": payload["land_use"],
                "district": payload["district"],
                "sector": payload["sector"],
                "cell": payload["cell"],
                "zone_type": payload["zone_type"],
                "max_floors_allowed_by_zone": payload.get("max_floors_allowed_by_zone"),
            },
        )

        # Permits: wipe and recreate. This is safe because we never edit
        # permits locally — the source registry is authoritative.
        parcel.permits.all().delete()
        permits_to_create = [
            Permit(
                permit_no=p["permit_no"],
                parcel=parcel,
                category=p["category"],
                status=p["status"],
                issued_date=_parse_date(p.get("issued_date")),
                expiry_date=_parse_date(p.get("expiry_date")),
                intended_use=p["intended_use"],
                max_floors_allowed=p["max_floors_allowed"],
                max_footprint_sqm=p.get("max_footprint_sqm"),
                applicant_name=p["applicant_name"],
            )
            for p in payload.get("permits", [])
        ]
        Permit.objects.bulk_create(permits_to_create)
        return len(permits_to_create)


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    return value


def _geojson_dumps(geojson: dict) -> str:
    """Convert a Python dict GeoJSON to a JSON string for GEOSGeometry."""
    import json
    return json.dumps(geojson)
