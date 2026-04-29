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
    CONFIRMED = "confirmed", "Confirmed"
    DISMISSED = "dismissed", "Dismissed"
    CLOSED = "closed", "Closed"


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

    verdict = models.CharField(
        max_length=32,
        choices=[
            ("confirmed", "Confirmed — construction is unauthorised"),
            ("dismissed", "Dismissed — no violation found"),
            ("needs_review", "Needs senior review"),
        ],
    )
    notes = models.TextField(blank=True, default="")
    visited_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

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
