"""Seed LEVIR-CD test pairs as demo ImageScenes overlaid on Kacyiru.

Takes cherry-picked LEVIR-CD test pair IDs (from curate_demo_pairs.py output),
reprojects their geo-transform so the imagery overlays the Kacyiru AOI, uploads
both T1 and T2 PNGs to MinIO, and creates AOI + ImageScene rows ready for a
detection job.

Honest sleight of hand — documented:
  LEVIR-CD imagery is from Chinese cities, not Kigali. This command reprojects
  the affine transform so the 1024×1024 image appears to cover the Kacyiru AOI
  area (~500 m × 500 m at 0.5 m/px). The spatial join against seeded parcels will
  work because the reprojected footprints overlap the Kacyiru grid. The visual
  appearance of the imagery (buildings, roads, vegetation) will be from China, not
  Rwanda — acceptable for an RHA technical demo where the point is the detection
  pipeline, not the imagery content.
  When RHA asks "is this real Kigali imagery?" the honest answer is: "No — this is
  a stand-in from a public benchmark dataset to show the detection pipeline. The
  real pipeline will use Planet Labs imagery over Kigali once the RHA data agreement
  is signed."

Usage:
    python manage.py seed_levir_demo_scenes --pair-ids test_1,test_5,test_10
    python manage.py seed_levir_demo_scenes --pair-ids test_1 --data-dir /app/data/LEVIR-CD --force

Arguments:
    --pair-ids      Comma-separated LEVIR-CD test pair IDs (e.g. test_1,test_5)
    --data-dir      Path to LEVIR-CD directory (default: ml/data/LEVIR-CD)
    --force         Delete existing demo scenes for these pair IDs before reseeding
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone as dt_tz
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand, CommandError

from imagery.models import AOI, ImageScene, ImageSource

# ---------------------------------------------------------------------------
# Kacyiru anchor — keep in sync with seed.py and seed_sample_scenes.py
# ---------------------------------------------------------------------------

ANCHOR_LAT = -1.9418   # AOI centre lat (slightly N of seed grid)
ANCHOR_LNG = 30.0908   # AOI centre lng

# LEVIR-CD images are 1024×1024 at 0.5 m/px → 512 m per side.
LEVIR_IMG_SIZE = 1024
LEVIR_PIXEL_SIZE_M = 0.5
LEVIR_EXTENT_M = LEVIR_IMG_SIZE * LEVIR_PIXEL_SIZE_M   # 512 m

METRES_PER_DEGREE = 111_000.0
EXTENT_DEG = LEVIR_EXTENT_M / METRES_PER_DEGREE        # ≈ 0.00461°


def _reprojected_transform() -> dict[str, float]:
    """Affine transform that places the LEVIR image over the Kacyiru AOI.

    origin_lat/lng = top-left corner of the image (row 0 = north).
    The image is centred on ANCHOR_LAT/LNG.
    """
    half = EXTENT_DEG / 2.0
    return {
        "origin_lat": ANCHOR_LAT + half,
        "origin_lng": ANCHOR_LNG - half,
        "pixel_size_m": LEVIR_PIXEL_SIZE_M,
        "metres_per_degree": METRES_PER_DEGREE,
    }


def _aoi_boundary() -> Polygon:
    half = EXTENT_DEG / 2.0
    lng_w = ANCHOR_LNG - half
    lat_s = ANCHOR_LAT - half
    lng_e = ANCHOR_LNG + half
    lat_n = ANCHOR_LAT + half
    return Polygon(
        ((lng_w, lat_s), (lng_e, lat_s), (lng_e, lat_n), (lng_w, lat_n), (lng_w, lat_s)),
        srid=4326,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _upload_to_minio(local_path: Path, object_key: str) -> None:
    from minio import Minio  # type: ignore

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=getattr(settings, "MINIO_SECURE", False),
    )
    bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.fput_object(bucket, object_key, str(local_path))


def _find_image(directory: Path, stem: str) -> Path | None:
    for suffix in (".png", ".jpg", ".tif", ".tiff"):
        p = directory / f"{stem}{suffix}"
        if p.exists():
            return p
    return None


class Command(BaseCommand):
    help = "Seed LEVIR-CD test pairs as demo scenes overlaid on the Kacyiru AOI."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--pair-ids",
            required=True,
            help="Comma-separated LEVIR-CD test pair IDs, e.g. test_1,test_5,test_10",
        )
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=None,
            help="Path to LEVIR-CD directory (default: ml/data/LEVIR-CD relative to repo root)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing demo AOIs for these pair IDs and recreate.",
        )

    def handle(self, *args, **options) -> None:
        pair_ids = [p.strip() for p in options["pair_ids"].split(",") if p.strip()]
        if not pair_ids:
            raise CommandError("--pair-ids must be a non-empty comma-separated list")

        # Resolve data directory.
        if options["data_dir"]:
            data_dir = options["data_dir"]
        else:
            # Try container path first, then host-relative path.
            for candidate in [
                Path("/app/data/LEVIR-CD"),
                Path(__file__).resolve().parents[6] / "ml" / "data" / "LEVIR-CD",
            ]:
                if candidate.exists():
                    data_dir = candidate
                    break
            else:
                raise CommandError(
                    "Cannot find LEVIR-CD data. Pass --data-dir explicitly or "
                    "ensure ml/data/LEVIR-CD exists."
                )

        a_dir = data_dir / "A"
        b_dir = data_dir / "B"

        if not a_dir.exists():
            raise CommandError(f"LEVIR-CD A directory not found at {a_dir}")

        geo_transform = _reprojected_transform()
        aoi_boundary = _aoi_boundary()

        for pair_id in pair_ids:
            self._seed_pair(
                pair_id=pair_id,
                a_dir=a_dir,
                b_dir=b_dir,
                geo_transform=geo_transform,
                aoi_boundary=aoi_boundary,
                force=options["force"],
            )

    def _seed_pair(
        self,
        pair_id: str,
        a_dir: Path,
        b_dir: Path,
        geo_transform: dict,
        aoi_boundary: Polygon,
        force: bool,
    ) -> None:
        aoi_name = f"LEVIR Demo: {pair_id}"

        if force:
            AOI.objects.filter(name=aoi_name).delete()
            self.stdout.write(f"Deleted existing AOI '{aoi_name}'")

        if AOI.objects.filter(name=aoi_name).exists():
            aoi = AOI.objects.get(name=aoi_name)
            scenes = list(aoi.scenes.order_by("captured_at"))
            self.stdout.write(f"[{pair_id}] Already seeded — use --force to recreate")
            if len(scenes) >= 2:
                self._print_pair_summary(pair_id, aoi, scenes[0], scenes[1])
            return

        t1_src = _find_image(a_dir, pair_id)
        t2_src = _find_image(b_dir, pair_id)

        if t1_src is None:
            self.stderr.write(f"[{pair_id}] T1 image not found in {a_dir} — skipping")
            return
        if t2_src is None:
            self.stderr.write(f"[{pair_id}] T2 image not found in {b_dir} — skipping")
            return

        t1_key = f"levir-demo/{pair_id}/t1{t1_src.suffix}"
        t2_key = f"levir-demo/{pair_id}/t2{t2_src.suffix}"

        try:
            _upload_to_minio(t1_src, t1_key)
            _upload_to_minio(t2_src, t2_key)
            self.stdout.write(f"[{pair_id}] Uploaded T1 → {t1_key}")
            self.stdout.write(f"[{pair_id}] Uploaded T2 → {t2_key}")
            t1_cog_path = t1_key
            t2_cog_path = t2_key
        except Exception as exc:
            self.stderr.write(f"[{pair_id}] MinIO upload failed: {exc} — using local paths")
            t1_cog_path = str(t1_src)
            t2_cog_path = str(t2_src)

        aoi = AOI.objects.create(
            name=aoi_name,
            district="Gasabo",
            boundary=aoi_boundary,
            description=(
                f"LEVIR-CD test pair '{pair_id}' reprojected over Kacyiru AOI. "
                "Imagery is from a Chinese city benchmark dataset — stand-in for "
                "real Kigali satellite data pending RHA data agreement."
            ),
        )

        # T1 = 2023 baseline, T2 = 2024 current (LEVIR pairs are pre/post change)
        t1_scene = ImageScene.objects.create(
            aoi=aoi,
            captured_at=datetime(2023, 1, 15, 10, 0, tzinfo=dt_tz.utc),
            source=ImageSource.OTHER,
            resolution_m=LEVIR_PIXEL_SIZE_M,
            cog_path=t1_cog_path,
            checksum=_sha256(t1_src),
            metadata={"geo_transform": geo_transform, "levir_pair_id": pair_id, "image": "A"},
        )
        t2_scene = ImageScene.objects.create(
            aoi=aoi,
            captured_at=datetime(2024, 3, 20, 10, 0, tzinfo=dt_tz.utc),
            source=ImageSource.OTHER,
            resolution_m=LEVIR_PIXEL_SIZE_M,
            cog_path=t2_cog_path,
            checksum=_sha256(t2_src),
            metadata={"geo_transform": geo_transform, "levir_pair_id": pair_id, "image": "B"},
        )

        self._print_pair_summary(pair_id, aoi, t1_scene, t2_scene)

    def _print_pair_summary(
        self, pair_id: str, aoi: AOI, t1: ImageScene, t2: ImageScene
    ) -> None:
        self.stdout.write(self.style.SUCCESS(f"\n[{pair_id}] Scenes ready:"))
        self.stdout.write(f"  AOI ID:      {aoi.pk}  ({aoi.name})")
        self.stdout.write(f"  T1 scene ID: {t1.pk}  ({t1.cog_path})")
        self.stdout.write(f"  T2 scene ID: {t2.pk}  ({t2.cog_path})")
        self.stdout.write(f"\n  Trigger detection:")
        self.stdout.write(f"    ./scripts/demo_e2e.sh {t1.pk} {t2.pk}")
