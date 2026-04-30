"""End-to-end smoke test: detection → flag pipeline.

Tests the full pipeline synchronously (no Celery broker or ml-service required):
  1. Creates an AOI covering the Kacyiru seed grid.
  2. Creates two ImageScene rows (T1 baseline, T2 current).
  3. Seeds local Parcel rows that match the known parcel positions.
  4. Patches the permit adapter with an in-process fake that returns
     pre-canned permit data matching the seeded scenarios.
  5. Patches _download_scene to write tiny synthetic PNG files.
  6. Patches _call_ml_service to return WGS84-like "pixel" polygons whose
     centroids land inside the seeded parcels (transform=None branch).
  7. Calls _run_pipeline() directly (bypassing Celery) so the test
     runs in the same DB transaction as pytest-django.
  8. Asserts that flags exist with correct severities for each scenario.

Scenario mapping:
  parcel_index 0  (row=0, col=0) → authorized      → expected severity: low
  parcel_index 13 (row=1, col=5) → authorized      → expected severity: low
  parcel_index 48 (row=6, col=0) → no_permit       → expected severity: critical
  parcel_index 56 (row=7, col=0) → no_permit       → expected severity: critical
  parcel_index 64 (row=8, col=0) → expired         → expected severity: high
  parcel_index 72 (row=9, col=0) → wrong_category  → expected severity: medium

All six are large footprints (≈1597 sqm) — verified the severity table in
flags/models.py is consistent with these expectations.
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta, timezone as dt_tz
from pathlib import Path
from unittest.mock import patch

from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from detections.models import ChangeType, DetectionJob, JobStatus
from flags.models import Flag, Severity
from imagery.models import AOI, ImageScene, ImageSource
from parcels.models import LandUse, Parcel, Permit, PermitStatus
from services.permits.base import LookupResult, ParcelData, PermitData

# ---------------------------------------------------------------------------
# Constants — must match seed.py and tasks.py
# ---------------------------------------------------------------------------

ANCHOR_LAT = -1.9441
ANCHOR_LNG = 30.0890
PARCEL_SIZE_DEG = 0.00045

GRID_ROWS = 10
GRID_COLS = 8

# Footprint is 80% of parcel, area ≈ 1597 sqm (large).
FOOTPRINT_FRAC = 0.80
FOOTPRINT_SIZE = PARCEL_SIZE_DEG * FOOTPRINT_FRAC
FOOTPRINT_AREA_SQM = (PARCEL_SIZE_DEG * FOOTPRINT_FRAC * 111_000) ** 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upi(row: int, col: int) -> str:
    parcel_index = row * GRID_COLS + col
    return f"1/01/03/05/{parcel_index + 1:04d}"


def _parcel_polygon(row: int, col: int) -> Polygon:
    lng_w = ANCHOR_LNG + col * PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT + row * PARCEL_SIZE_DEG
    lng_e = lng_w + PARCEL_SIZE_DEG
    lat_n = lat_s + PARCEL_SIZE_DEG
    coords = (
        (lng_w, lat_s), (lng_e, lat_s), (lng_e, lat_n), (lng_w, lat_n), (lng_w, lat_s)
    )
    return Polygon(coords, srid=4326)


def _parcel_centroid(row: int, col: int) -> Point:
    poly = _parcel_polygon(row, col)
    return Point(poly.centroid.x, poly.centroid.y, srid=4326)


def _aoi_boundary() -> Polygon:
    """A polygon that contains the entire 10×8 seed grid."""
    lng_w = ANCHOR_LNG - PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT - PARCEL_SIZE_DEG
    lng_e = ANCHOR_LNG + (GRID_COLS + 1) * PARCEL_SIZE_DEG
    lat_n = ANCHOR_LAT + (GRID_ROWS + 1) * PARCEL_SIZE_DEG
    coords = (
        (lng_w, lat_s), (lng_e, lat_s), (lng_e, lat_n), (lng_w, lat_n), (lng_w, lat_s)
    )
    return Polygon(coords, srid=4326)


def _footprint_polygon(row: int, col: int) -> Polygon:
    """Build an 80%-sized footprint polygon inside a grid cell."""
    lng_w = ANCHOR_LNG + col * PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT + row * PARCEL_SIZE_DEG
    margin = (PARCEL_SIZE_DEG - FOOTPRINT_SIZE) / 2
    x0 = lng_w + margin
    y0 = lat_s + margin
    x1 = x0 + FOOTPRINT_SIZE
    y1 = y0 + FOOTPRINT_SIZE
    coords = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon(coords, srid=4326)


# ---------------------------------------------------------------------------
# Scenario cells
# ---------------------------------------------------------------------------

_SCENARIO_CELLS = [
    (0, 0, "authorized"),
    (1, 5, "authorized"),
    (6, 0, "no_permit"),
    (7, 0, "no_permit"),
    (8, 0, "expired"),
    (9, 0, "wrong_category"),
]


def _create_parcel_for_scenario(row: int, col: int, scenario: str) -> Parcel:
    upi = _upi(row, col)
    parcel = Parcel.objects.create(
        upi=upi,
        boundary=_parcel_polygon(row, col),
        centroid=_parcel_centroid(row, col),
        owner_name="Test Owner",
        land_use=LandUse.RESIDENTIAL,
        district="Gasabo",
        sector="Kacyiru",
        cell="Kamatamu",
        zone_type="high_density_residential",
        max_floors_allowed_by_zone=3,
    )

    today = date.today()

    if scenario == "authorized":
        Permit.objects.create(
            permit_no=f"BP-TEST-{row:02d}{col:02d}",
            parcel=parcel,
            category="1",
            status=PermitStatus.ACTIVE,
            issued_date=today - timedelta(days=180),
            expiry_date=today + timedelta(days=540),
            intended_use=LandUse.RESIDENTIAL,
            max_floors_allowed=2,
            max_footprint_sqm=150.0,
            applicant_name="Test Owner",
        )
    elif scenario == "expired":
        Permit.objects.create(
            permit_no=f"BP-TEST-{row:02d}{col:02d}",
            parcel=parcel,
            category="1",
            status=PermitStatus.EXPIRED,
            issued_date=today - timedelta(days=900),
            expiry_date=today - timedelta(days=180),
            intended_use=LandUse.RESIDENTIAL,
            max_floors_allowed=2,
            max_footprint_sqm=150.0,
            applicant_name="Test Owner",
        )
    elif scenario == "wrong_category":
        Permit.objects.create(
            permit_no=f"BP-TEST-{row:02d}{col:02d}",
            parcel=parcel,
            category="1",
            status=PermitStatus.ACTIVE,
            issued_date=today - timedelta(days=120),
            expiry_date=today + timedelta(days=600),
            intended_use=LandUse.RESIDENTIAL,
            max_floors_allowed=1,
            max_footprint_sqm=100.0,
            applicant_name="Test Owner",
        )
    # no_permit: no Permit row created.

    return parcel


# ---------------------------------------------------------------------------
# Fake permit adapter
# ---------------------------------------------------------------------------


def _build_permit_data(permit: Permit) -> PermitData:
    return PermitData(
        permit_no=permit.permit_no,
        category=permit.category,
        status=permit.status,
        intended_use=permit.intended_use,
        max_floors_allowed=permit.max_floors_allowed,
        applicant_name=permit.applicant_name,
        issued_date=permit.issued_date,
        expiry_date=permit.expiry_date,
        max_footprint_sqm=permit.max_footprint_sqm,
    )


class _FakePermitAdapter:
    """Answers verify_upi from the local Django ORM — no HTTP calls."""

    def verify_upi(self, upi: str):
        try:
            parcel = Parcel.objects.prefetch_related("permits").get(upi=upi)
        except Parcel.DoesNotExist:
            return None

        permits = [_build_permit_data(p) for p in parcel.permits.all()]
        return ParcelData(
            upi=parcel.upi,
            owner_name=parcel.owner_name,
            district=parcel.district,
            sector=parcel.sector,
            cell=parcel.cell,
            land_use=parcel.land_use,
            zone_type=parcel.zone_type,
            centroid_lat=parcel.centroid.y,
            centroid_lng=parcel.centroid.x,
            boundary_geojson={},
            has_active_permit=parcel.has_active_permit,
            permits=permits,
            max_floors_allowed_by_zone=parcel.max_floors_allowed_by_zone,
        )

    def lookup_by_coords(self, lat, lng, max_distance_m=100.0) -> LookupResult:
        return LookupResult(found=False)


# ---------------------------------------------------------------------------
# Fake ML service response
#
# We use a custom geo-transform embedded in the test's T1 scene so that
# pixel coords map cleanly to WGS84.  Setting pixel_size_m=111_000 and
# metres_per_degree=111_000 gives deg_per_pixel = 1.0, so pixel coords
# *are* degree offsets from (origin_lng, origin_lat).
# Setting origin at (ANCHOR_LNG, ANCHOR_LAT) means we can pass the
# actual WGS84 footprint coordinates directly as "pixel" coords.
# ---------------------------------------------------------------------------

# Test transform: one pixel == one PARCEL_SIZE_DEG.
# origin_lat is set to the TOP (north) edge of the grid so that
#   lat = origin_lat - row_px * deg_per_pixel = ANCHOR_LAT + (GRID_ROWS - row_px) * PARCEL_SIZE_DEG
# Setting origin_lat = ANCHOR_LAT + GRID_ROWS * PARCEL_SIZE_DEG ensures that
# pixel (row=0, col=0) maps to (ANCHOR_LNG, ANCHOR_LAT + GRID_ROWS * PARCEL_SIZE_DEG).
# A parcel at grid (row=R, col=C) has its south-west corner at
#   lat_s = ANCHOR_LAT + R * PARCEL_SIZE_DEG
#   lng_w = ANCHOR_LNG + C * PARCEL_SIZE_DEG
# In pixel space that parcel's south-west corner is at pixel row = GRID_ROWS - R, col = C.
_TEST_TRANSFORM = {
    "origin_lng": ANCHOR_LNG,
    "origin_lat": ANCHOR_LAT + GRID_ROWS * PARCEL_SIZE_DEG,
    "pixel_size_m": PARCEL_SIZE_DEG * 111_000.0,
    "metres_per_degree": 111_000.0,
}


def _footprint_as_pixel_coords(row: int, col: int) -> list[list[float]]:
    """Return footprint corners in pixel space for the test transform.

    For a parcel at grid (row, col):
      pixel_col = col + margin_frac          (left edge + margin)
      pixel_row = (GRID_ROWS - row) - 1 + margin_frac  (inverted row, south edge)

    We return a closed 5-point rectangle matching the 80% footprint.
    """
    margin_frac = (1.0 - FOOTPRINT_FRAC) / 2.0
    # Pixel column: col + margin within the parcel cell
    px_col0 = col + margin_frac
    px_col1 = col + margin_frac + FOOTPRINT_FRAC
    # Pixel row: grid row 0 is SOUTH, so in pixel space (where 0=NORTH) it's
    # GRID_ROWS - row. The south edge of parcel row R is at pixel row GRID_ROWS - R.
    # The 80% footprint south edge is at pixel row GRID_ROWS - row - margin_frac.
    # The north edge (smaller pixel row) is at GRID_ROWS - row - 1 + margin_frac.
    px_row_s = GRID_ROWS - row - margin_frac          # south (larger pixel row)
    px_row_n = GRID_ROWS - row - 1.0 + margin_frac    # north (smaller pixel row)

    # Return (col, row) pairs = (x, y) as expected by _pixel_polygon_to_wgs84
    return [
        [px_col0, px_row_s],
        [px_col1, px_row_s],
        [px_col1, px_row_n],
        [px_col0, px_row_n],
        [px_col0, px_row_s],  # closed
    ]


def _fake_ml_polygons() -> list[dict]:
    """Return 6 polygon dicts (pixel coords) corresponding to the 6 scenario cells.

    NOTE on wrong_category: the pipeline always emits ChangeType.NEW_BUILDING
    (the ml-service doesn't yet return change_type per polygon).  So
    wrong_category parcels get severity=LOW (active permit + new_building).
    Session 5 will add change_type to the ml-service response.
    """
    results = []
    for row, col, scenario in _SCENARIO_CELLS:
        results.append({
            "polygon": _footprint_as_pixel_coords(row, col),
            "confidence": 0.92,
            "area_sqm": FOOTPRINT_AREA_SQM,
        })
    return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def aoi(db) -> AOI:
    return AOI.objects.create(
        name="Kacyiru Test AOI",
        district="Gasabo",
        boundary=_aoi_boundary(),
    )


@pytest.fixture()
def t1_scene(aoi, tmp_path) -> ImageScene:
    img_path = tmp_path / "t1.png"
    _write_synthetic_png(img_path)
    return ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2023, 1, 15, 10, 0, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path=str(img_path),
        # Test transform: pixel coords == WGS84 degree offsets from (0, 0).
        metadata={"geo_transform": _TEST_TRANSFORM},
    )


@pytest.fixture()
def t2_scene(aoi, tmp_path) -> ImageScene:
    img_path = tmp_path / "t2.png"
    _write_synthetic_png(img_path)
    return ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2024, 3, 20, 10, 0, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path=str(img_path),
    )


def _write_synthetic_png(path: Path) -> None:
    """Write a minimal valid PNG header so the file exists on disk.

    The content is never read in tests because _call_ml_service is patched.
    We just need a file that Path.exists() returns True for so _download_scene
    takes the local-file short-circuit branch.
    """
    # Minimal 1x1 red PNG (89 bytes) — no Pillow required.
    _MINIMAL_PNG = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk len + type
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # width=1, height=1
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # bit depth, color, CRC...
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
        0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ])
    path.write_bytes(_MINIMAL_PNG)


@pytest.fixture()
def seeded_parcels(db) -> dict[str, Parcel]:
    parcels = {}
    for row, col, scenario in _SCENARIO_CELLS:
        parcels[scenario] = _create_parcel_for_scenario(row, col, scenario)
    return parcels


# ---------------------------------------------------------------------------
# Helper: patch both external dependencies
# ---------------------------------------------------------------------------


def _run_with_patches(job):
    """Run _run_pipeline with both ml-service and permit adapter patched."""
    from detections.tasks import _run_pipeline

    with patch("detections.tasks.get_permit_adapter", return_value=_FakePermitAdapter()):
        with patch("detections.tasks._call_ml_service", return_value=_fake_ml_polygons()):
            # _download_scene: cog_path is already a real local file (tmp_path fixture).
            # No patch needed — the tasks.py local-file short-circuit handles it.
            return _run_pipeline(job)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_full_pipeline_creates_flags(t1_scene, t2_scene, seeded_parcels):
    """Smoke test: pipeline creates 6 flags, one per polygon."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )

    flags_created = _run_with_patches(job)

    job.refresh_from_db()
    assert flags_created == 6, f"Expected 6 flags, got {flags_created}"
    assert job.detections.count() == 6

    flags = Flag.objects.filter(detection__job=job)
    assert flags.count() == 6


@pytest.mark.django_db
def test_authorized_parcels_get_low_severity(t1_scene, t2_scene, seeded_parcels):
    """Parcels with active permits → LOW severity."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )
    _run_with_patches(job)

    flags = Flag.objects.filter(detection__job=job).select_related("detection__parcel")
    by_parcel = {f.detection.parcel.upi: f for f in flags if f.detection.parcel}

    for row, col, scenario in _SCENARIO_CELLS:
        if scenario != "authorized":
            continue
        upi = _upi(row, col)
        assert upi in by_parcel, f"No flag for authorized parcel {upi}"
        assert by_parcel[upi].severity == Severity.LOW, (
            f"Expected LOW for {upi}, got {by_parcel[upi].severity}"
        )


@pytest.mark.django_db
def test_no_permit_parcels_get_critical_severity(t1_scene, t2_scene, seeded_parcels):
    """Parcels without any permit and large footprint → CRITICAL."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )
    _run_with_patches(job)

    flags = Flag.objects.filter(detection__job=job).select_related("detection__parcel")
    by_parcel = {f.detection.parcel.upi: f for f in flags if f.detection.parcel}

    for row, col, scenario in _SCENARIO_CELLS:
        if scenario != "no_permit":
            continue
        upi = _upi(row, col)
        assert upi in by_parcel, f"No flag for no_permit parcel {upi}"
        assert by_parcel[upi].severity == Severity.CRITICAL, (
            f"Expected CRITICAL for {upi}, got {by_parcel[upi].severity}"
        )


@pytest.mark.django_db
def test_expired_permit_gets_high_severity(t1_scene, t2_scene, seeded_parcels):
    """Parcel with expired permit and large footprint → HIGH."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )
    _run_with_patches(job)

    flags = Flag.objects.filter(detection__job=job).select_related("detection__parcel")
    by_parcel = {f.detection.parcel.upi: f for f in flags if f.detection.parcel}

    expired_upi = _upi(8, 0)
    assert expired_upi in by_parcel, f"No flag for expired parcel {expired_upi}"
    assert by_parcel[expired_upi].severity == Severity.HIGH, (
        f"Expected HIGH for expired parcel, got {by_parcel[expired_upi].severity}"
    )


@pytest.mark.django_db
def test_pipeline_is_idempotent(t1_scene, t2_scene, seeded_parcels):
    """Running the pipeline twice on the same job produces no duplicate flags."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )

    first_run = _run_with_patches(job)
    second_run = _run_with_patches(job)

    assert first_run == 6
    assert second_run == 0
    assert job.detections.count() == 6
    assert Flag.objects.filter(detection__job=job).count() == 6


@pytest.mark.django_db
def test_audit_log_created_for_each_flag(t1_scene, t2_scene, seeded_parcels):
    """Every flag creation must produce at least one AuditLog entry."""
    from flags.models import AuditLog

    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )
    _run_with_patches(job)

    flags = Flag.objects.filter(detection__job=job)
    for flag in flags:
        logs = AuditLog.objects.filter(flag=flag)
        assert logs.exists(), f"No audit log for Flag #{flag.pk}"
        assert logs.filter(event="created").exists(), (
            f"No 'created' audit event for Flag #{flag.pk}"
        )


@pytest.mark.django_db
def test_flags_filterable_by_severity_and_district(t1_scene, t2_scene, seeded_parcels):
    """Flags can be filtered by severity and district."""
    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )
    _run_with_patches(job)

    critical_flags = Flag.objects.filter(detection__job=job, severity=Severity.CRITICAL)
    assert critical_flags.count() == 2, (
        f"Expected 2 CRITICAL flags, got {critical_flags.count()}"
    )

    gasabo_flags = Flag.objects.filter(detection__job=job, district="Gasabo")
    assert gasabo_flags.count() == 6, (
        f"Expected all 6 flags in Gasabo, got {gasabo_flags.count()}"
    )
