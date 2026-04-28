"""API schemas for the mock permit service.

These response shapes ARE the integration contract. When we negotiate real
KUBAKA access, this is the document we hand them: 'we need an API that
returns these JSON shapes.'

Keep these stable. The real adapter will translate KUBAKA's actual responses
into these shapes — that's the whole point of the adapter pattern.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PermitStatus = Literal["pending", "approved", "active", "expired", "revoked"]
LandUse = Literal[
    "residential",
    "commercial",
    "mixed_use",
    "industrial",
    "institutional",
    "agricultural",
    "green_zone",
    "transport",
]
PermitCategory = Literal["1", "2", "3", "4", "5", "6", "7"]


class PermitResponse(BaseModel):
    """A permit attached to a parcel."""

    permit_no: str = Field(..., examples=["BP-2024-001234"])
    category: PermitCategory = Field(..., description="Rwanda Building Code category 1-7")
    status: PermitStatus
    issued_date: date | None = None
    expiry_date: date | None = None
    intended_use: LandUse
    max_floors_allowed: int
    max_footprint_sqm: float | None = None
    applicant_name: str


class ParcelResponse(BaseModel):
    """A land parcel with its current permit status."""

    upi: str = Field(..., examples=["1/01/03/05/0142"])
    owner_name: str
    district: str
    sector: str
    cell: str
    land_use: LandUse
    zone_type: str
    max_floors_allowed_by_zone: int | None = None
    centroid_lat: float
    centroid_lng: float
    boundary_geojson: dict = Field(..., description="GeoJSON polygon")
    permits: list[PermitResponse]

    # Derived field for convenience — saves the consumer a calculation.
    has_active_permit: bool = Field(
        ..., description="True if any permit is currently active and not expired"
    )


class ParcelLookupResponse(BaseModel):
    """Response when looking up a parcel by coordinates."""

    found: bool
    parcel: ParcelResponse | None = None
    distance_m: float | None = Field(
        None, description="Distance from query point to parcel centroid"
    )


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    timestamp: datetime
