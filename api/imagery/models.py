"""AOI and ImageScene models.

An Area of Interest (AOI) is a named polygon that the Rwanda Housing
Authority wants to monitor. Each AOI can accumulate many ImageScene records
over time — one per satellite/drone acquisition.

ImageScene records point at Cloud-Optimised GeoTIFFs (COGs) stored in MinIO.
A pair of ImageScenes (T1 + T2) feeds a DetectionJob.
"""

from django.contrib.gis.db import models as gis_models
from django.db import models


class ImageSource(models.TextChoices):
    PLANET = "planet", "Planet Labs"
    MAXAR = "maxar", "Maxar"
    DRONE = "drone", "Drone"
    OTHER = "other", "Other"


class AOI(models.Model):
    """Area of Interest — a named geographic boundary to monitor.

    District is stored denormalised here for fast row-level filtering;
    it must match the district values used in Parcel and User models.
    """

    name = models.CharField(max_length=128)
    district = models.CharField(max_length=64, db_index=True)

    # Full boundary polygon for spatial operations (overlap checks, etc.)
    boundary = gis_models.PolygonField(srid=4326)

    description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "imagery_aoi"
        verbose_name = "AOI"
        verbose_name_plural = "AOIs"
        ordering = ["district", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.district})"


class ImageScene(models.Model):
    """A single captured image (COG) associated with an AOI.

    cog_path is a MinIO object key, not a full URL — the storage backend
    constructs presigned URLs at serve time.

    resolution_m is the ground sampling distance in metres (e.g. 0.5 for
    50 cm resolution).

    checksum is the SHA-256 hex digest of the COG file, used to detect
    duplicate uploads and corrupted transfers.
    """

    aoi = models.ForeignKey(AOI, on_delete=models.PROTECT, related_name="scenes")
    captured_at = models.DateTimeField(
        help_text="UTC timestamp when the sensor captured this image."
    )
    source = models.CharField(max_length=32, choices=ImageSource.choices, default=ImageSource.OTHER)
    resolution_m = models.FloatField(
        help_text="Ground sampling distance in metres."
    )
    cog_path = models.CharField(
        max_length=512,
        help_text="MinIO object key for the Cloud-Optimised GeoTIFF.",
    )
    checksum = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 hex digest of the COG file.",
    )

    # Optional affine transform for geo-projecting pixel-space ML outputs.
    # Keys: origin_lng, origin_lat, pixel_size_m, metres_per_degree.
    # Set by seed_sample_scenes; absent for third-party imagery (use COG header).
    metadata = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Optional scene metadata (geo-transform, acquisition params).",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "imagery_imagescene"
        verbose_name = "Image Scene"
        verbose_name_plural = "Image Scenes"
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["aoi", "captured_at"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self) -> str:
        return f"{self.aoi.name} — {self.captured_at:%Y-%m-%d} ({self.source})"
