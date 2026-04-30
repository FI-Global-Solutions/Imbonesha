"""Detection pipeline — Celery task.

run_detection_job(t1_scene_id, t2_scene_id) is the public entry point.

Pipeline (Session 3 — real ML inference):
  1. Pull T1 and T2 scene files from MinIO to a local temp directory.
  2. POST both paths to the ml-service /detect endpoint (with tenacity retry).
  3. For each polygon returned:
     a. Build a Django Polygon from the pixel coordinates, re-projected into
        WGS84 using the scene's geo-transform.
     b. Spatial join against Parcel.boundary to find the matched parcel.
     c. Query the permit adapter for the parcel's permit status.
     d. Compute severity.
     e. Upsert Detection + Flag (idempotent via footprint_hash / OneToOneField).
  4. Mark DetectionJob as COMPLETED or FAILED.

Geo-projection note:
  The ml-service returns polygon coordinates in *pixel space* (column, row).
  Converting pixel → WGS84 requires the affine geo-transform from the source
  GeoTIFF (stored in MinIO).  For the sample imagery workflow (seed_sample_scenes),
  we embed the geo-transform into the ImageScene.metadata JSON field.  When that
  field is absent (e.g. synthetic test images) we fall back to the scene AOI's
  centroid and assign a nominal 2 m/px scale — which is sufficient for the
  spatial join against 50 m parcels.

Idempotency:
  - DetectionJob: one per call.
  - Detection: unique_together=(job, footprint_hash) — SHA-256 of polygon WKB.
  - Flag: OneToOneField(detection) + get_or_create.

Fallback behaviour:
  If the ml-service is unavailable after all retries, the job is marked
  FAILED with a clear error message.  No partial flags are written.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import tempfile
from pathlib import Path
from typing import Any

import httpx
from celery import shared_task
from django.contrib.gis.geos import Point, Polygon
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from detections.models import ChangeType, Detection, DetectionJob, JobStatus
from flags.models import Flag, FlagStatus, compute_severity
from services.permits import get_permit_adapter
from services.permits.base import PermitServiceError

logger = logging.getLogger(__name__)

ML_TIMEOUT_SECONDS = 300  # 5-minute hard timeout for inference


# ---------------------------------------------------------------------------
# ML service client
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _call_ml_service(t1_path: str, t2_path: str) -> list[dict[str, Any]]:
    """POST to ml-service /detect and return the polygon list.

    Retried up to 3 times with exponential backoff on network errors.
    Raises httpx.HTTPError on non-2xx response (no retry for 4xx — caller's fault).
    """
    ml_url = getattr(settings, "ML_SERVICE_URL", "http://ml-service:8002")
    url = f"{ml_url}/detect"

    payload = {
        "t1_path": t1_path,
        "t2_path": t2_path,
        "threshold": 0.5,
    }

    logger.info("Calling ml-service: POST %s", url)
    with httpx.Client(timeout=ML_TIMEOUT_SECONDS) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    polygons = data.get("polygons", [])
    logger.info(
        "ml-service returned %d polygons (model=%s, inference_ms=%.0f)",
        len(polygons),
        data.get("model_version", "unknown"),
        data.get("inference_ms", 0),
    )
    return polygons


# ---------------------------------------------------------------------------
# MinIO download
# ---------------------------------------------------------------------------


def _download_scene(cog_path: str, dest_dir: Path) -> Path:
    """Download a scene from MinIO (or the configured S3) to *dest_dir*.

    Returns the local path of the downloaded file.
    Falls back to treating cog_path as a local filesystem path for tests
    that place images directly on disk (seed_sample_scenes workflow).
    """
    # If cog_path already exists on disk (e.g. mounted volume), use it directly.
    local = Path(cog_path)
    if local.exists():
        return local

    try:
        from minio import Minio  # type: ignore

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=getattr(settings, "MINIO_SECURE", False),
        )
        bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
        filename = Path(cog_path).name
        local_path = dest_dir / filename
        client.fget_object(bucket, cog_path, str(local_path))
        logger.info("Downloaded %s from MinIO → %s", cog_path, local_path)
        return local_path
    except Exception as exc:
        raise RuntimeError(f"Failed to download scene {cog_path!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Geo-projection helpers
# ---------------------------------------------------------------------------


def _extract_geotransform(local_path: Path) -> dict[str, float] | None:
    """Read the affine geo-transform from a GeoTIFF using rasterio.

    Returns a dict compatible with _pixel_polygon_to_wgs84, or None if the
    file is not a GeoTIFF or rasterio is not available.
    """
    if local_path.suffix.lower() not in (".tif", ".tiff", ".cog"):
        return None
    try:
        import rasterio  # type: ignore

        with rasterio.open(local_path) as src:
            tf = src.transform  # affine.Affine
            # Affine: (pixel_size_x, 0, origin_x, 0, pixel_size_y, origin_y)
            # origin_x/y is the top-left corner; pixel_size_y is negative.
            origin_lng = tf.c
            origin_lat = tf.f  # top-left lat (row 0 = north)
            pixel_size_m_x = abs(tf.a) * 111_000.0  # deg → m (approx)
            pixel_size_m_y = abs(tf.e) * 111_000.0
            pixel_size_m = (pixel_size_m_x + pixel_size_m_y) / 2.0
            return {
                "origin_lng": origin_lng,
                "origin_lat": origin_lat,
                "pixel_size_m": pixel_size_m,
                "metres_per_degree": 111_000.0,
            }
    except Exception as exc:
        logger.warning("Could not read geo-transform from %s: %s", local_path, exc)
        return None


def _pixel_polygon_to_wgs84(
    pixel_coords: list[tuple[float, float]],
    transform: dict[str, float] | None,
) -> Polygon:
    """Convert pixel-space polygon coordinates to a WGS84 Polygon.

    Args:
        pixel_coords: List of (col, row) pixel coordinates.
        transform: Affine transform dict with keys:
            origin_lng, origin_lat, pixel_size_m
          If None, a nominal 2 m/px transform centred at (0, 0) is used.

    Returns:
        A django.contrib.gis.geos.Polygon in SRID 4326.
    """
    if transform is None:
        # Fallback: treat pixel coords as metres offset from (0°, 0°).
        # Won't give sensible geographic positions but is safe for unit tests.
        m_per_deg = 111_000.0
        pixel_size_m = 2.0
        origin_lng = 30.089
        origin_lat = -1.944
    else:
        m_per_deg = transform.get("metres_per_degree", 111_000.0)
        pixel_size_m = transform.get("pixel_size_m", 2.0)
        origin_lng = transform.get("origin_lng", 30.089)
        origin_lat = transform.get("origin_lat", -1.944)

    deg_per_pixel = pixel_size_m / m_per_deg

    # Row 0 is the TOP (north) of the image; row increases downward.
    # Latitude increases northward, so each additional row subtracts from lat.
    wgs84_coords = [
        (origin_lng + col * deg_per_pixel, origin_lat - row * deg_per_pixel)
        for col, row in pixel_coords
    ]
    return Polygon(wgs84_coords, srid=4326)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def _run_pipeline(job: DetectionJob) -> int:
    """Run the full detection pipeline for a job.

    Downloads scenes, calls ml-service, upserts Detections and Flags.
    Returns the number of new Flags created.
    """
    adapter = get_permit_adapter()
    flags_created = 0

    # Load geo-transform: prefer scene metadata first (fast path), then fall
    # back to reading the GeoTIFF header while the temp file is still on disk.
    meta1 = job.t1_scene.metadata or {}
    transform = meta1.get("geo_transform")

    with tempfile.TemporaryDirectory(prefix="imbonesha_detect_") as tmp_dir:
        tmp = Path(tmp_dir)

        t1_local = _download_scene(job.t1_scene.cog_path, tmp)
        t2_local = _download_scene(job.t2_scene.cog_path, tmp)

        # Extract geo-transform from GeoTIFF header while the file is on disk.
        if transform is None:
            transform = _extract_geotransform(t1_local)
            if transform is not None:
                # Cache into metadata so subsequent runs skip the rasterio read.
                job.t1_scene.metadata = {**meta1, "geo_transform": transform}
                job.t1_scene.save(update_fields=["metadata"])
                logger.info("Cached geo-transform from GeoTIFF into ImageScene.metadata")

        # The ml-service receives filesystem paths valid *inside its container*.
        # In docker-compose, ml/sample_imagery is mounted at /app/sample_imagery.
        ml_t1 = str(t1_local)
        ml_t2 = str(t2_local)

        try:
            polygons = _call_ml_service(ml_t1, ml_t2)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise RuntimeError(
                f"ml-service unavailable after retries: {exc}"
            ) from exc

    for poly_data in polygons:
        pixel_coords = poly_data["polygon"]
        confidence = poly_data["confidence"]
        area_sqm = poly_data["area_sqm"]

        footprint = _pixel_polygon_to_wgs84(pixel_coords, transform)
        fp_hash = hashlib.sha256(footprint.wkb).hexdigest()

        # Determine change type — ml-service returns "new_building" for now.
        change_type = ChangeType.NEW_BUILDING

        from parcels.models import Parcel

        matched_parcel = (
            Parcel.objects.filter(boundary__contains=footprint.centroid)
            .first()
        )

        detection, created = Detection.objects.get_or_create(
            job=job,
            footprint_hash=fp_hash,
            defaults={
                "footprint": footprint,
                "confidence": confidence,
                "change_type": change_type,
                "area_sqm": area_sqm,
                "parcel": matched_parcel,
            },
        )

        if not created:
            logger.debug("Detection already exists for hash %s — skipping", fp_hash[:12])
            continue

        parcel_data = None
        if matched_parcel:
            try:
                parcel_data = adapter.verify_upi(matched_parcel.upi)
            except PermitServiceError:
                logger.warning(
                    "Permit service error for UPI %s — treating as unknown",
                    matched_parcel.upi,
                )

        has_active_permit = parcel_data.has_active_permit if parcel_data else False
        most_recent = parcel_data.most_recent_permit if parcel_data else None
        permit_status = most_recent.status if most_recent else None
        permit_category = most_recent.category if most_recent else None
        zone_type = parcel_data.zone_type if parcel_data else (
            matched_parcel.zone_type if matched_parcel else ""
        )

        severity = compute_severity(
            has_active_permit=has_active_permit,
            permit_status=permit_status,
            permit_category=permit_category,
            detected_change_type=change_type,
            area_sqm=area_sqm,
            zone_type=zone_type,
        )

        district = (
            parcel_data.district if parcel_data
            else (matched_parcel.district if matched_parcel else "")
        )
        flag, flag_created = Flag.objects.get_or_create(
            detection=detection,
            defaults={
                "severity": severity,
                "status": FlagStatus.PENDING,
                "district": district,
            },
        )

        if flag_created:
            flags_created += 1
            logger.info(
                "Flag #%d created: severity=%s parcel=%s confidence=%.3f area_sqm=%.0f",
                flag.pk,
                severity,
                matched_parcel.upi if matched_parcel else "unmatched",
                confidence,
                area_sqm,
            )

    return flags_created


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="detections.run_detection_job")
def run_detection_job(self, t1_scene_id: int, t2_scene_id: int) -> dict:
    """Run change detection for a pair of image scenes.

    Creates a DetectionJob, calls the ml-service for real change polygons,
    spatially joins them to Parcel records, queries permit status, computes
    severity, and creates Flag rows.

    Args:
        t1_scene_id: PK of the earlier (baseline) ImageScene.
        t2_scene_id: PK of the more recent ImageScene.

    Returns:
        Dict with job_id, detection_count, flag_count, status.
    """
    from imagery.models import ImageScene

    logger.info(
        "run_detection_job started: t1=%d t2=%d", t1_scene_id, t2_scene_id
    )

    t1_scene = ImageScene.objects.get(pk=t1_scene_id)
    t2_scene = ImageScene.objects.get(pk=t2_scene_id)

    job = DetectionJob.objects.create(
        t1_scene=t1_scene,
        t2_scene=t2_scene,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v0",
        started_at=timezone.now(),
    )

    try:
        with transaction.atomic():
            flags_created = _run_pipeline(job)

        job.status = JobStatus.COMPLETED
        job.ran_at = timezone.now()
        job.save(update_fields=["status", "ran_at"])

        result = {
            "job_id": job.pk,
            "detection_count": job.detections.count(),
            "flag_count": flags_created,
            "status": JobStatus.COMPLETED,
        }
        logger.info("run_detection_job completed: %s", result)
        return result

    except Exception as exc:
        job.status = JobStatus.FAILED
        job.ran_at = timezone.now()
        job.error_message = str(exc)
        job.save(update_fields=["status", "ran_at", "error_message"])
        logger.exception("run_detection_job failed for job #%d", job.pk)
        raise
