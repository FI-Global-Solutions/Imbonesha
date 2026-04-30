"""Create sample image scenes for the Kacyiru demo AOI.

Generates two synthetic 256×256 PNG image pairs (T1 baseline + T2 current)
that simulate satellite imagery over the Kacyiru seed grid.  T2 has bright
rectangular "buildings" added in positions that correspond to the seeded
parcel scenarios (no_permit, expired, wrong_category).

The images are:
  1. Written to ml/sample_imagery/ on the host (mounted into ml-service).
  2. Uploaded to MinIO under the imbonesha-imagery bucket.
  3. Registered as ImageScene rows in the database.

The ImageScene.metadata includes a geo_transform so the ml-service can
convert pixel-space detections to WGS84 coordinates.

Usage:
    python manage.py seed_sample_scenes [--force]

    --force  Recreate scenes even if they already exist.

Output:
    Prints the AOI ID and T1/T2 scene IDs to use in a detection job.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import zlib
from datetime import datetime, timezone as dt_tz
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from imagery.models import AOI, ImageScene, ImageSource

# ---------------------------------------------------------------------------
# Geography constants — must match seed.py and tasks.py
# ---------------------------------------------------------------------------

ANCHOR_LAT = -1.9441
ANCHOR_LNG = 30.0890
PARCEL_SIZE_DEG = 0.00045
GRID_ROWS = 10
GRID_COLS = 8

# Image is 256×256 pixels; each pixel = PARCEL_SIZE_DEG / (256/GRID_COLS) degrees.
# We cover the full 8-column grid horizontally: 8 parcels × 50 m/parcel = 400 m.
# At 256 pixels across, each pixel is 400/256 ≈ 1.56 m.
# In degrees: PARCEL_SIZE_DEG * GRID_COLS / 256 ≈ 0.0000141°/px.

IMG_SIZE = 256
PIXEL_SIZE_M = (PARCEL_SIZE_DEG * GRID_COLS * 111_000) / IMG_SIZE  # ≈ 1.56 m/px
METRES_PER_DEGREE = 111_000.0

# Geo-transform origin: TOP-LEFT corner of the image (row 0 = north).
# After the session 4 sign fix: lat = origin_lat - row * deg_per_pixel,
# so origin_lat must be the NORTHERN edge of the image, not the southern.
ORIGIN_LNG = ANCHOR_LNG - PARCEL_SIZE_DEG * 0.5
ORIGIN_LAT = ANCHOR_LAT + (GRID_ROWS + 0.5) * PARCEL_SIZE_DEG  # north edge

# Parcel positions in pixel space (centre of each parcel cell).
# col_px = (parcel_lng_centre - ORIGIN_LNG) / deg_per_pixel
DEG_PER_PX = PIXEL_SIZE_M / METRES_PER_DEGREE


# Scenario cells (row, col) from seed.py — where we inject changes in T2.
_CHANGE_CELLS = [
    (6, 0),  # no_permit
    (7, 0),  # no_permit
    (8, 0),  # expired
    (9, 0),  # wrong_category
]


# ---------------------------------------------------------------------------
# Minimal PNG writer (no Pillow required)
# ---------------------------------------------------------------------------


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    chunk_len = struct.pack(">I", len(data))
    chunk_data = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(chunk_data) & 0xFFFFFFFF)
    return chunk_len + chunk_data + crc


def _write_png(pixels: list[list[tuple[int, int, int]]], path: Path) -> None:
    """Write an RGB PNG file from a list-of-rows of (R, G, B) tuples."""
    h = len(pixels)
    w = len(pixels[0])

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)

    # IDAT — deflate-compressed scanlines (filter type 0 = None)
    raw = b""
    for row in pixels:
        raw += b"\x00"  # filter byte
        for r, g, b in row:
            raw += bytes([r, g, b])
    idat = _png_chunk(b"IDAT", zlib.compress(raw))

    iend = _png_chunk(b"IEND", b"")

    signature = b"\x89PNG\r\n\x1a\n"
    path.write_bytes(signature + ihdr + idat + iend)


def _make_scene_pixels(
    add_buildings: list[tuple[int, int, int, int]],
    base_r: int = 100,
    base_g: int = 130,
    base_b: int = 90,
) -> list[list[tuple[int, int, int]]]:
    """Generate a 256×256 synthetic scene.

    args:
        add_buildings: List of (col_px, row_px, width, height) for bright
            rectangles added to simulate new construction.
        base_r/g/b: Background RGB (greenish — vegetation).
    """
    import random
    rng = random.Random(42)

    pixels = [
        [
            (
                base_r + rng.randint(-10, 10),
                base_g + rng.randint(-10, 10),
                base_b + rng.randint(-10, 10),
            )
            for _ in range(IMG_SIZE)
        ]
        for _ in range(IMG_SIZE)
    ]

    for col_px, row_px, w, h in add_buildings:
        for r in range(row_px, min(row_px + h, IMG_SIZE)):
            for c in range(col_px, min(col_px + w, IMG_SIZE)):
                # Light grey — concrete roof
                pixels[r][c] = (200 + rng.randint(-10, 10), 200 + rng.randint(-10, 10), 200 + rng.randint(-10, 10))

    return pixels


def _parcel_pixel_centre(row: int, col: int) -> tuple[int, int]:
    """Return the pixel (col_px, row_px) for the centre of a parcel cell."""
    lng_centre = ANCHOR_LNG + (col + 0.5) * PARCEL_SIZE_DEG
    lat_centre = ANCHOR_LAT + (row + 0.5) * PARCEL_SIZE_DEG
    col_px = int((lng_centre - ORIGIN_LNG) / DEG_PER_PX)
    row_px = int((lat_centre - ORIGIN_LAT) / DEG_PER_PX)
    return col_px, row_px


def _aoi_boundary() -> Polygon:
    lng_w = ANCHOR_LNG - PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT - PARCEL_SIZE_DEG
    lng_e = ANCHOR_LNG + (GRID_COLS + 1) * PARCEL_SIZE_DEG
    lat_n = ANCHOR_LAT + (GRID_ROWS + 1) * PARCEL_SIZE_DEG
    coords = (
        (lng_w, lat_s), (lng_e, lat_s), (lng_e, lat_n), (lng_w, lat_n), (lng_w, lat_s)
    )
    return Polygon(coords, srid=4326)


# ---------------------------------------------------------------------------
# MinIO upload
# ---------------------------------------------------------------------------


def _ensure_bucket(client, bucket: str) -> None:
    from minio.error import S3Error  # type: ignore

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _upload_to_minio(local_path: Path, object_key: str) -> None:
    from minio import Minio  # type: ignore

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=getattr(settings, "MINIO_SECURE", False),
    )
    bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
    _ensure_bucket(client, bucket)

    client.fput_object(bucket, object_key, str(local_path))


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Seed synthetic sample image scenes for demo and integration testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recreate sample scenes even if they already exist.",
        )

    def handle(self, *args, **options) -> None:
        force = options["force"]

        # Check if already seeded.
        if not force and AOI.objects.filter(name="Kacyiru Sample AOI").exists():
            self.stdout.write("Sample scenes already seeded. Use --force to recreate.")
            aoi = AOI.objects.get(name="Kacyiru Sample AOI")
            scenes = list(aoi.scenes.order_by("captured_at"))
            if len(scenes) >= 2:
                self._print_summary(aoi, scenes[0], scenes[1])
            return

        # Delete existing if --force.
        if force:
            AOI.objects.filter(name="Kacyiru Sample AOI").delete()

        # Set up imagery output directory.
        # In docker-compose: worker mounts ../ml/sample_imagery → /ml_imagery
        #                    ml-service mounts ../ml/sample_imagery → /app/sample_imagery
        # The SAMPLE_IMAGERY_DIR env var overrides for local dev (outside Docker).
        imagery_dir = Path(
            os.environ.get("SAMPLE_IMAGERY_DIR", "/ml_imagery")
        )
        imagery_dir.mkdir(parents=True, exist_ok=True)

        # --- Generate T1 (baseline — no new buildings) ---
        t1_pixels = _make_scene_pixels(add_buildings=[])
        t1_path = imagery_dir / "kacyiru_t1_2023.png"
        _write_png(t1_pixels, t1_path)
        self.stdout.write(f"Written T1: {t1_path}")

        # --- Generate T2 (current — new buildings at scenario cells) ---
        building_rects = []
        for row, col in _CHANGE_CELLS:
            cx, cy = _parcel_pixel_centre(row, col)
            bw = max(8, int(PARCEL_SIZE_DEG * 0.8 / DEG_PER_PX))
            bh = bw
            building_rects.append((cx - bw // 2, cy - bh // 2, bw, bh))

        t2_pixels = _make_scene_pixels(add_buildings=building_rects)
        t2_path = imagery_dir / "kacyiru_t2_2024.png"
        _write_png(t2_pixels, t2_path)
        self.stdout.write(f"Written T2: {t2_path}")

        # --- Compute checksums ---
        def sha256(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()

        t1_checksum = sha256(t1_path)
        t2_checksum = sha256(t2_path)

        # --- Upload to MinIO ---
        t1_key = "sample/kacyiru/2023-01-15/t1.png"
        t2_key = "sample/kacyiru/2024-03-20/t2.png"
        try:
            _upload_to_minio(t1_path, t1_key)
            _upload_to_minio(t2_path, t2_key)
            self.stdout.write("Uploaded both scenes to MinIO.")
            # Store MinIO keys as cog_path — the worker will download them.
            t1_cog_path = t1_key
            t2_cog_path = t2_key
        except Exception as exc:
            self.stderr.write(
                f"MinIO upload failed ({exc}) — using local paths instead. "
                "Make sure ml/sample_imagery is volume-mounted in the worker."
            )
            # Fall back to the container-local path.
            # In worker container: ../api:/app, ../ml/sample_imagery:/ml_imagery
            t1_cog_path = f"/ml_imagery/kacyiru_t1_2023.png"
            t2_cog_path = f"/ml_imagery/kacyiru_t2_2024.png"

        # Geo-transform embedded in T1 metadata so tasks.py can project pixels.
        geo_transform = {
            "origin_lng": ORIGIN_LNG,
            "origin_lat": ORIGIN_LAT,
            "pixel_size_m": PIXEL_SIZE_M,
            "metres_per_degree": METRES_PER_DEGREE,
        }

        # --- Create DB records ---
        aoi = AOI.objects.create(
            name="Kacyiru Sample AOI",
            district="Gasabo",
            boundary=_aoi_boundary(),
            description="Synthetic sample AOI for the Session 3 demo.",
        )

        t1_scene = ImageScene.objects.create(
            aoi=aoi,
            captured_at=datetime(2023, 1, 15, 10, 0, tzinfo=dt_tz.utc),
            source=ImageSource.OTHER,
            resolution_m=round(PIXEL_SIZE_M, 2),
            cog_path=t1_cog_path,
            checksum=t1_checksum,
            metadata={"geo_transform": geo_transform},
        )

        t2_scene = ImageScene.objects.create(
            aoi=aoi,
            captured_at=datetime(2024, 3, 20, 10, 0, tzinfo=dt_tz.utc),
            source=ImageSource.OTHER,
            resolution_m=round(PIXEL_SIZE_M, 2),
            cog_path=t2_cog_path,
            checksum=t2_checksum,
        )

        self._print_summary(aoi, t1_scene, t2_scene)

    def _print_summary(
        self, aoi: AOI, t1_scene: ImageScene, t2_scene: ImageScene
    ) -> None:
        self.stdout.write(self.style.SUCCESS("\nSample scenes ready:"))
        self.stdout.write(f"  AOI ID:      {aoi.pk}")
        self.stdout.write(f"  T1 scene ID: {t1_scene.pk}  ({t1_scene.cog_path})")
        self.stdout.write(f"  T2 scene ID: {t2_scene.pk}  ({t2_scene.cog_path})")
        self.stdout.write("")
        self.stdout.write("Trigger a detection job (from Django shell):")
        self.stdout.write(
            f"  from detections.tasks import run_detection_job\n"
            f"  run_detection_job.delay({t1_scene.pk}, {t2_scene.pk})"
        )
        self.stdout.write("")
        self.stdout.write("Or via the demo script:")
        self.stdout.write(f"  ./scripts/demo_e2e.sh {t1_scene.pk} {t2_scene.pk}")
