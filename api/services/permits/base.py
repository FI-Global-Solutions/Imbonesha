"""Abstract base class and data types for the permit verification adapter.

Both MockPermitAdapter and KubakaPermitAdapter implement
PermitVerificationService. Callers import the interface, never a concrete
class directly — the factory injects the right one based on PERMIT_ADAPTER.

Data classes mirror the shapes in mock-services/permit-service/app/schemas.py
so the mock and real adapters present identical outputs to callers.
"""

import abc
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class PermitData:
    """A single construction permit attached to a parcel."""

    permit_no: str
    category: str  # "1"–"7"
    status: str  # "active", "expired", "revoked", "pending", "approved"
    intended_use: str
    max_floors_allowed: int
    applicant_name: str
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    max_footprint_sqm: Optional[float] = None

    @property
    def is_active(self) -> bool:
        """True if the permit is currently active and not yet expired."""
        if self.status != "active":
            return False
        if self.expiry_date is None:
            return True
        return self.expiry_date >= date.today()


@dataclass
class ParcelData:
    """A land parcel with its associated permits."""

    upi: str
    owner_name: str
    district: str
    sector: str
    cell: str
    land_use: str
    zone_type: str
    centroid_lat: float
    centroid_lng: float
    boundary_geojson: dict
    has_active_permit: bool
    permits: list[PermitData] = field(default_factory=list)
    max_floors_allowed_by_zone: Optional[int] = None

    @property
    def active_permits(self) -> list[PermitData]:
        return [p for p in self.permits if p.is_active]

    @property
    def most_recent_permit(self) -> Optional[PermitData]:
        """The most recently issued permit regardless of status."""
        if not self.permits:
            return None
        return max(self.permits, key=lambda p: p.issued_date or date.min)


@dataclass
class LookupResult:
    """Result of a coordinate-based parcel lookup."""

    found: bool
    parcel: Optional[ParcelData] = None
    distance_m: Optional[float] = None


class PermitVerificationService(abc.ABC):
    """Abstract interface for permit data retrieval.

    Implementations must be safe to call from a Celery worker context
    (i.e., no Django ORM assumptions unless explicitly documented).
    """

    @abc.abstractmethod
    def verify_upi(self, upi: str) -> Optional[ParcelData]:
        """Return parcel + permit data for the given UPI, or None if not found.

        Args:
            upi: The 5-part Unique Parcel Identifier, e.g. "1/01/03/05/0042".

        Returns:
            ParcelData if found, None if the parcel is not in the registry.

        Raises:
            PermitServiceError: If the underlying service is unreachable after
                retries or returns an unexpected error.
        """

    @abc.abstractmethod
    def lookup_by_coords(
        self,
        lat: float,
        lng: float,
        max_distance_m: float = 100.0,
    ) -> LookupResult:
        """Find the parcel at or nearest to the given coordinates.

        Args:
            lat: Latitude in WGS84.
            lng: Longitude in WGS84.
            max_distance_m: Maximum search radius in metres.

        Returns:
            LookupResult with found=True and parcel data if a match exists
            within max_distance_m, or found=False otherwise.
        """


class PermitServiceError(Exception):
    """Raised when the permit service cannot be reached or returns an error."""
