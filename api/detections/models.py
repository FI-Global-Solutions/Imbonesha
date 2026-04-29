"""DetectionJob and Detection models.

A DetectionJob pairs two ImageScenes (T1 baseline vs T2 current) and tracks
the async Celery task that processes them. Each job produces zero or more
Detection records — one per candidate new building footprint.

Idempotency: Detection is unique on (job, footprint_hash) so re-running a
job against the same scenes produces no duplicate rows.
"""

import hashlib

from django.contrib.gis.db import models as gis_models
from django.db import models

from imagery.models import ImageScene


class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ChangeType(models.TextChoices):
    NEW_BUILDING = "new_building", "New Building"
    EXTENSION = "extension", "Extension"
    DEMOLITION = "demolition", "Demolition"
    COMMERCIAL = "commercial", "Commercial Structure"
    UNKNOWN = "unknown", "Unknown"


class DetectionJob(models.Model):
    """Tracks a single change-detection run between two image scenes.

    t1_scene is the earlier (baseline) image; t2_scene is the more recent
    image where new construction may be visible.

    model_version records which ML model version produced this job's
    detections. Use "stub-v0" for the hardcoded stub pipeline.
    """

    t1_scene = models.ForeignKey(
        ImageScene,
        on_delete=models.PROTECT,
        related_name="jobs_as_t1",
    )
    t2_scene = models.ForeignKey(
        ImageScene,
        on_delete=models.PROTECT,
        related_name="jobs_as_t2",
    )

    status = models.CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
        db_index=True,
    )
    model_version = models.CharField(max_length=64, default="stub-v0")

    # Set when the Celery task begins and completes.
    started_at = models.DateTimeField(null=True, blank=True)
    ran_at = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "detections_job"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Job #{self.pk} [{self.status}] — {self.t1_scene.aoi.name}"


class Detection(models.Model):
    """A candidate new building footprint produced by a DetectionJob.

    footprint is the polygon bounding the detected change, in WGS84.
    area_sqm is pre-computed to avoid repeated geodesic calculations at
    query time.

    footprint_hash is the SHA-256 of the WKB footprint bytes — used as
    the idempotency key so re-running a job never duplicates a detection.

    parcel is populated when a spatial join matches the footprint to a
    known parcel; null if the footprint falls outside all known parcels.
    """

    job = models.ForeignKey(DetectionJob, on_delete=models.CASCADE, related_name="detections")
    footprint = gis_models.PolygonField(srid=4326)
    footprint_hash = models.CharField(max_length=64, db_index=True)

    confidence = models.FloatField(
        default=1.0,
        help_text="Model confidence in [0, 1]. Stub always emits 1.0.",
    )
    change_type = models.CharField(
        max_length=32,
        choices=ChangeType.choices,
        default=ChangeType.NEW_BUILDING,
    )
    area_sqm = models.FloatField(
        help_text="Approximate footprint area in square metres."
    )

    # Populated after the spatial join against Parcel.
    parcel = models.ForeignKey(
        "parcels.Parcel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detections",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "detections_detection"
        ordering = ["-created_at"]
        # One detection per (job, footprint) pair — guarantees idempotency.
        unique_together = [("job", "footprint_hash")]
        indexes = [
            models.Index(fields=["job", "change_type"]),
            models.Index(fields=["parcel"]),
        ]

    def __str__(self) -> str:
        parcel_str = self.parcel_id or "unmatched"
        return f"Detection #{self.pk} — {self.change_type} on {parcel_str}"

    @classmethod
    def compute_hash(cls, footprint_wkb: bytes) -> str:
        """Stable hash for a footprint geometry used as idempotency key."""
        return hashlib.sha256(footprint_wkb).hexdigest()
