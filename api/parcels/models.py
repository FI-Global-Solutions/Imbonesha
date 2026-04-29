"""Parcel and Permit models — the local mirror of the KUBAKA / mock registry.

We mirror parcels into our own database for two reasons:

1. **Spatial joins must be local.** Detection runs produce hundreds of
   polygons; doing a UPI lookup over HTTP for each one would crawl. Local
   PostGIS lets us run ST_Contains in milliseconds.

2. **Audit and offline operation.** Inspectors in the field may not have
   connectivity. The mobile app talks to the main API, which in turn
   already knows the parcels.

The local mirror is kept in sync with the source registry via the
`sync_parcels_from_permit_service` management command, run nightly in
production. Parcels are upserted by UPI; permits are replaced wholesale
on each sync (they're cheap to recreate and we don't track local edits
to them).

Field shapes are deliberately aligned with the response shape in
docs/integration-contract.md.
"""

from django.contrib.gis.db import models as gis_models
from django.db import models


class LandUse(models.TextChoices):
    RESIDENTIAL = "residential", "Residential"
    COMMERCIAL = "commercial", "Commercial"
    MIXED_USE = "mixed_use", "Mixed Use"
    INDUSTRIAL = "industrial", "Industrial"
    INSTITUTIONAL = "institutional", "Institutional"
    AGRICULTURAL = "agricultural", "Agricultural"
    GREEN_ZONE = "green_zone", "Green Zone"
    TRANSPORT = "transport", "Transport"


class PermitStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"


class PermitCategory(models.TextChoices):
    """Rwanda Building Code categories (Ministerial Order N° 02/CAB.M/019)."""

    CAT_1 = "1", "Cat 1 — Single-family residential, ground floor"
    CAT_2 = "2", "Cat 2 — Residential up to G+1"
    CAT_3 = "3", "Cat 3 — Towers / G+2 and above / capacity > 100"
    CAT_4 = "4", "Cat 4 — Industrial / hazardous / public buildings"
    CAT_5 = "5", "Cat 5 — Large commercial complexes"
    CAT_6 = "6", "Cat 6 — Critical infrastructure"
    CAT_7 = "7", "Cat 7 — Mixed-use developments"


class Parcel(models.Model):
    """A land parcel identified by its UPI (Unique Parcel Identifier).

    UPI format: Province/District/Sector/Cell/Parcel, e.g. 1/01/03/05/0142.
    """

    # UPI is the natural primary key in Rwanda — there's no benefit to
    # also having a synthetic ID.
    upi = models.CharField(max_length=32, primary_key=True)

    boundary = gis_models.PolygonField(srid=4326)
    centroid = gis_models.PointField(srid=4326)

    owner_name = models.CharField(max_length=255)
    land_use = models.CharField(max_length=32, choices=LandUse.choices)
    district = models.CharField(max_length=64)
    sector = models.CharField(max_length=64)
    cell = models.CharField(max_length=64)

    # Master plan zone classification — drives whether construction is
    # even allowed. 'green_zone' means no construction permitted at all.
    zone_type = models.CharField(max_length=64)
    max_floors_allowed_by_zone = models.PositiveIntegerField(null=True, blank=True)

    # When we last synced this parcel from the source registry. Useful for
    # detecting stale data — if a sync hasn't run for >24h, that's an
    # operations alarm.
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "parcels_parcel"
        indexes = [
            models.Index(fields=["district"]),
            models.Index(fields=["sector"]),
            models.Index(fields=["zone_type"]),
        ]
        ordering = ["upi"]

    def __str__(self) -> str:
        return f"{self.upi} — {self.owner_name}"

    @property
    def has_active_permit(self) -> bool:
        """True if this parcel currently has any active, non-expired permit."""
        from datetime import date

        today = date.today()
        return self.permits.filter(
            status=PermitStatus.ACTIVE,
        ).filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).exists()


class Permit(models.Model):
    """A construction permit issued for a parcel.

    Permits are replaced wholesale on each sync from the source registry.
    Don't add local-only fields here without a sync strategy.
    """

    permit_no = models.CharField(max_length=64, primary_key=True)
    parcel = models.ForeignKey(
        Parcel,
        on_delete=models.CASCADE,
        related_name="permits",
        to_field="upi",
        db_column="upi",
    )

    category = models.CharField(max_length=4, choices=PermitCategory.choices)
    status = models.CharField(max_length=16, choices=PermitStatus.choices)

    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    intended_use = models.CharField(max_length=32, choices=LandUse.choices)
    max_floors_allowed = models.PositiveIntegerField(default=1)
    max_footprint_sqm = models.FloatField(null=True, blank=True)

    applicant_name = models.CharField(max_length=255)

    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "parcels_permit"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["expiry_date"]),
        ]
        ordering = ["-issued_date"]

    def __str__(self) -> str:
        return f"{self.permit_no} ({self.get_status_display()})"
