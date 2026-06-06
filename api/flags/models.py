"""Flag, Inspection, and AuditLog models.

The Flag is the core enforcement artefact. It ties a Detection to a severity
rating and routes the case to an inspector. State transitions are logged
immutably in AuditLog via Django signals (see flags/signals.py).

Severity computation (compute_severity):

    no_permit, large footprint (≥ 100 sqm) → critical
    no_permit, small footprint            → high
    expired_permit, large footprint        → high
    expired_permit, small footprint        → medium
    wrong_category (permit exists, wrong type) → medium
    authorized (valid permit)             → low   (shouldn't normally flag)
    fallback                              → medium

These are intentionally coarse for the stub. The real scoring will also
factor in zone_type (green_zone construction is always critical) and
historical violations on the parcel.
"""

import math
import uuid

from django.conf import settings
from django.db import models


class Severity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class FlagStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ASSIGNED = "assigned", "Assigned"
    IN_REVIEW = "in_review", "In Review"
    CONFIRMED = "confirmed", "Confirmed Unauthorized"
    DISMISSED = "dismissed", "Dismissed"
    MONITORING = "monitoring", "Under Monitoring"
    INACCESSIBLE = "inaccessible", "Inaccessible"
    DATA_ERROR = "data_error", "Data Error"
    CLOSED = "closed", "Closed"


VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":      {"assigned", "dismissed"},
    "assigned":     {"in_review", "confirmed", "dismissed", "monitoring", "inaccessible", "data_error", "pending"},
    "in_review":    {"confirmed", "dismissed", "monitoring", "inaccessible", "data_error"},
    "confirmed":    {"closed"},
    "dismissed":    {"closed", "pending"},
    "monitoring":   {"assigned"},
    "inaccessible": {"assigned"},
    "data_error":   {"closed"},
    "closed":       set(),
}


class Flag(models.Model):
    """An enforcement flag raised against a detection.

    One detection produces at most one flag (unique_together enforced below).
    This constraint is what makes the detection pipeline idempotent — if
    run_detection_job is called twice with the same job, the second pass
    finds existing Detection rows (unique on footprint_hash) and then tries
    to create Flag rows that already exist, which is silently skipped via
    get_or_create.

    assigned_to may be null when a flag is first created; it is set when
    a district_admin assigns the case to an inspector.
    """

    detection = models.OneToOneField(
        "detections.Detection",
        on_delete=models.CASCADE,
        related_name="flag",
    )
    severity = models.CharField(max_length=16, choices=Severity.choices, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=FlagStatus.choices,
        default=FlagStatus.PENDING,
        db_index=True,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_flags",
        limit_choices_to={"role": "inspector"},
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flags_assigned_by",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    # Denormalised district from detection → parcel for fast row-level filtering.
    # Populated at flag creation; never changes after that.
    district = models.CharField(max_length=64, blank=True, default="", db_index=True)

    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "flags_flag"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["severity", "status"]),
            models.Index(fields=["district", "status"]),
        ]

    def __str__(self) -> str:
        parcel = self.detection.parcel_id or "unmatched"
        return f"Flag #{self.pk} [{self.severity}/{self.status}] — {parcel}"

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: str, actor, message: str = "") -> None:
        if not self.can_transition_to(new_status):
            raise ValueError(f"Cannot transition from {self.status!r} to {new_status!r}")
        old_status = self.status
        self.status = new_status
        self._actor = actor
        self._pre_save_snapshot = {
            "status": old_status,
            "severity": self.severity,
            "assigned_to_id": self.assigned_to_id,
        }
        self.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            flag=self,
            actor=actor,
            event="status_changed",
            before={"status": old_status},
            after={"status": new_status},
            message=message or f"Status changed from {old_status} to {new_status}",
        )


class InspectionVerdict(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed Unauthorized"
    DISMISSED = "dismissed", "Dismissed — False Positive"
    MONITORING = "monitoring", "Under Monitoring"
    INACCESSIBLE = "inaccessible", "Site Inaccessible"
    DATA_ERROR = "data_error", "Data Error — Wrong Location"


class Inspection(models.Model):
    """Field inspection verdict submitted by an inspector.

    A flag may accumulate multiple inspection records if it is reassigned or
    if the initial verdict is overridden by a senior officer.
    """

    flag = models.ForeignKey(Flag, on_delete=models.CASCADE, related_name="inspections")
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspections",
    )

    verdict = models.CharField(max_length=32, choices=InspectionVerdict.choices)
    notes = models.TextField(blank=True, default="")

    construction_stage = models.CharField(
        max_length=64, blank=True, default="",
        help_text="foundation / walls / roofing / finishing / completed / demolished / none_visible",
    )
    estimated_floors = models.PositiveIntegerField(null=True, blank=True)
    occupancy_observed = models.BooleanField(default=False)

    visited_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    inspector_lat = models.FloatField(null=True, blank=True)
    inspector_lng = models.FloatField(null=True, blank=True)
    inspector_accuracy_m = models.FloatField(null=True, blank=True)
    inspector_location_name = models.CharField(max_length=255, blank=True, default="")
    distance_to_site_m = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "flags_inspection"
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Inspection on Flag #{self.flag_id} by {self.inspector}"


class AuditLog(models.Model):
    """Immutable record of every state transition on a Flag.

    This table is append-only at the application layer. In production
    a Postgres row-level security policy prevents UPDATE and DELETE even
    from superusers, making the log legally admissible as a chain of custody.

    actor may be null for system-generated events (e.g. the Celery pipeline).
    """

    flag = models.ForeignKey(Flag, on_delete=models.CASCADE, related_name="audit_logs")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )

    # What changed — free-text key like "status_change", "assigned", "created".
    event = models.CharField(max_length=64)

    # JSON snapshot of the fields that changed.
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    message = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "flags_auditlog"
        ordering = ["-timestamp"]
        # Deliberately no unique constraint — multiple events per flag are normal.

    def __str__(self) -> str:
        return f"AuditLog Flag #{self.flag_id} — {self.event} at {self.timestamp:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Severity computation — lives here so it is importable from tasks without
# a circular import.
# ---------------------------------------------------------------------------

class Report(models.Model):
    """A generated PDF enforcement report covering one or more flags."""

    import uuid as _uuid

    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    flag_ids = models.JSONField(default=list)
    flag_count = models.IntegerField(default=0)
    file_path = models.CharField(max_length=512, blank=True, default="")
    file_size = models.BigIntegerField(default=0)

    class Meta:
        db_table = "flags_report"
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return f"Report '{self.title}' ({self.flag_count} flags)"


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class InspectionPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(Flag, on_delete=models.CASCADE, related_name="photos")
    inspection = models.ForeignKey(
        Inspection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="photos",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inspection_photos",
    )

    # MinIO object key — e.g. inspection-photos/{flag_id}/{photo_id}.jpg
    object_key = models.CharField(max_length=512)
    caption = models.CharField(max_length=255, blank=True, default="")

    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy_meters = models.FloatField(null=True, blank=True)
    captured_at = models.DateTimeField()

    # Computed server-side on upload via haversine_meters
    distance_from_site_m = models.FloatField(null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "flags_inspectionphoto"
        ordering = ["-captured_at"]

    def __str__(self) -> str:
        return f"Photo {self.id} for Flag #{self.flag_id} ({self.distance_from_site_m:.0f}m)" if self.distance_from_site_m else f"Photo {self.id} for Flag #{self.flag_id}"


def compute_severity(
    *,
    has_active_permit: bool,
    permit_status: str | None,
    permit_category: str | None,
    detected_change_type: str,
    area_sqm: float,
    zone_type: str = "",
) -> str:
    """Compute a Flag severity string from detection + permit facts.

    Args:
        has_active_permit: True if the parcel currently holds an active permit.
        permit_status: The status of the most relevant permit ("active",
            "expired", "revoked", etc.) or None if no permit exists.
        permit_category: The category string ("1"-"7") of the most relevant
            permit, or None.
        detected_change_type: The Detection.change_type value.
        area_sqm: Footprint area from Detection.area_sqm.
        zone_type: Parcel zone classification (e.g. "green_zone" → always
            critical).

    Returns:
        A Severity value string.
    """
    large = area_sqm >= 100.0

    # Construction in a protected zone is always critical regardless of permit.
    if zone_type == "green_zone":
        return Severity.CRITICAL

    if not has_active_permit:
        if permit_status is None:
            # No permit ever issued.
            return Severity.CRITICAL if large else Severity.HIGH
        else:
            # Permit exists but is not active (expired / revoked / pending).
            return Severity.HIGH if large else Severity.MEDIUM

    # Has an active permit — check for category mismatch.
    if detected_change_type == "commercial" and permit_category in ("1", "2"):
        # Residential permit but a commercial-looking structure detected.
        return Severity.MEDIUM

    # Valid permit, matching type, small footprint — low concern.
    return Severity.LOW
