"""Flag, Inspection, and AuditLog models.

The Flag is the core enforcement artefact. It ties a Detection to a severity
rating and routes the case to an inspector. State transitions are logged
immutably in AuditLog via Django signals (see flags/signals.py).

Severity + permit status computation (compute_severity):

    zone_violation  → critical  (green_zone/protected regardless of permit)
    no_parcel       → high      (no matching parcel in registry)
    no_permit       → critical if area ≥ 200 sqm, else high
    expired         → high
    wrong_category  → medium
    authorized      → low       (auto-verified at creation time)

permit_status and severity_reason are stored at flag creation time —
they reflect the legally relevant state at the moment of detection and
are never recomputed after that.
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


class PermitStatus(models.TextChoices):
    AUTHORIZED = "authorized", "Authorized — Active Permit"
    NO_PERMIT = "no_permit", "No Construction Permit"
    EXPIRED = "expired", "Expired Permit"
    WRONG_CATEGORY = "wrong_category", "Wrong Permit Category"
    ZONE_VIOLATION = "zone_violation", "Protected Zone Violation"
    NO_PARCEL = "no_parcel", "Unregistered Land"


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

    # Permit classification at detection time — stored once, never recomputed.
    permit_status = models.CharField(
        max_length=32,
        choices=PermitStatus.choices,
        default=PermitStatus.NO_PERMIT,
        db_index=True,
    )
    severity_reason = models.TextField(blank=True, default="")

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
    permit_no: str | None = None,
    detected_change_type: str,
    area_sqm: float,
    zone_type: str = "",
    matched_parcel: bool = True,
) -> tuple[str, str, str]:
    """Compute (severity, permit_status, reason) from detection + permit facts.

    Returns a 3-tuple stored on the Flag at creation time and never recomputed.

    Args:
        has_active_permit: True if the parcel currently holds an active permit.
        permit_status: Status of the most relevant permit, or None if no permit.
        permit_category: Category string ("1"–"7") of the most relevant permit.
        permit_no: Permit number for the human-readable reason string.
        detected_change_type: The Detection.change_type value.
        area_sqm: Footprint area from Detection.area_sqm.
        zone_type: Parcel zone classification.
        matched_parcel: False if no parcel was found in the spatial join.

    Returns:
        (severity, permit_status_enum, reason_text)
    """
    # Case 0: no matching parcel — unregistered land
    if not matched_parcel:
        return (
            Severity.HIGH,
            PermitStatus.NO_PARCEL,
            "Construction detected on land with no registered parcel — "
            "possible unregistered plot or boundary error",
        )

    # Case 1: protected zone — always critical
    if zone_type in ("green_zone", "protected", "wetland", "forest"):
        zone_label = zone_type.replace("_", " ").title()
        return (
            Severity.CRITICAL,
            PermitStatus.ZONE_VIOLATION,
            f"Construction detected in {zone_label} — no construction "
            "permitted in this zone regardless of permit status",
        )

    large = area_sqm >= 200.0

    # Case 2: no permit at all
    if not has_active_permit and permit_status is None:
        if large:
            return (
                Severity.CRITICAL,
                PermitStatus.NO_PERMIT,
                f"No construction permit on file — large structure ({area_sqm:.0f} m²) "
                "detected without any permit history",
            )
        return (
            Severity.HIGH,
            PermitStatus.NO_PERMIT,
            "No construction permit on file for this parcel",
        )

    # Case 3: permit exists but is not active (expired / revoked / pending)
    if not has_active_permit and permit_status is not None:
        permit_ref = f" (permit {permit_no})" if permit_no else ""
        return (
            Severity.HIGH,
            PermitStatus.EXPIRED,
            f"Construction permit{permit_ref} is {permit_status} — "
            "construction may require permit renewal",
        )

    # Case 4: active permit — check for category mismatch
    if has_active_permit:
        mismatch = False
        if detected_change_type == "commercial" and permit_category in ("1", "2"):
            mismatch = True
        if permit_category == "1" and area_sqm > 200:
            mismatch = True

        if mismatch:
            permit_ref = f"permit {permit_no}" if permit_no else "active permit"
            cat_labels = {
                "1": "single-family residential (Cat 1)",
                "2": "residential up to G+1 (Cat 2)",
                "3": "multi-storey residential (Cat 3)",
                "4": "industrial/commercial (Cat 4)",
                "5": "large commercial complex (Cat 5)",
            }
            cat_desc = cat_labels.get(permit_category or "", f"category {permit_category}")
            return (
                Severity.MEDIUM,
                PermitStatus.WRONG_CATEGORY,
                f"Active {permit_ref} is for {cat_desc}, but detected "
                f"construction appears to be {detected_change_type or 'a different type'}",
            )

        # Active permit, no mismatch — authorized
        permit_ref = f"permit {permit_no}" if permit_no else "an active permit"
        return (
            Severity.LOW,
            PermitStatus.AUTHORIZED,
            f"Active {permit_ref} on file — construction is authorized",
        )

    # Fallback: conservative — treat as no permit
    return (
        Severity.HIGH,
        PermitStatus.NO_PERMIT,
        "Permit status could not be determined — flagged conservatively",
    )
