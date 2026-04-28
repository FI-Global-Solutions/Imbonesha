"""ORM models for the mock permit service.

The shape of these tables is our best-effort guess at what KUBAKA exposes.
When we get real API access, we'll align the real adapter to whatever schema
KUBAKA actually uses — but the *response shape* of our endpoints is what
the rest of Imbonesha depends on, and that's defined in app/schemas.py.

Reference for permit categories: Rwanda Building Code, Ministerial Order
N° 02/CAB.M/019 of 15/04/2019 (Categories 1 through 7).
"""

from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Parcel(Base):
    """A land parcel identified by its UPI (Unique Parcel Identifier).

    UPI format in Rwanda has 5 parts separated by '/':
        Province / District / Sector / Cell / Parcel number
    Example: 1/01/03/05/0142
    """

    __tablename__ = "parcels"

    upi: Mapped[str] = mapped_column(String(32), primary_key=True)
    boundary: Mapped[str] = mapped_column(Geometry("POLYGON", srid=4326))
    centroid: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))

    owner_name: Mapped[str] = mapped_column(String(255))
    land_use: Mapped[str] = mapped_column(String(64))  # residential, commercial, mixed, etc.
    district: Mapped[str] = mapped_column(String(64))
    sector: Mapped[str] = mapped_column(String(64))
    cell: Mapped[str] = mapped_column(String(64))

    # Master plan zone classification — drives whether a permit could even
    # be issued here. e.g. "green_zone", "high_density_residential".
    zone_type: Mapped[str] = mapped_column(String(64))
    max_floors: Mapped[int | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    permits: Mapped[list["Permit"]] = relationship(
        back_populates="parcel", cascade="all, delete-orphan"
    )


class Permit(Base):
    """A construction permit issued for a parcel.

    Status lifecycle:
        pending → approved → active → expired
                          ↘ revoked
    """

    __tablename__ = "permits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    permit_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    upi: Mapped[str] = mapped_column(String(32), ForeignKey("parcels.upi"), index=True)

    # Rwanda Building Code categories 1–7
    category: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))  # pending, approved, active, expired, revoked

    issued_date: Mapped[date | None] = mapped_column(Date, default=None)
    expiry_date: Mapped[date | None] = mapped_column(Date, default=None)

    intended_use: Mapped[str] = mapped_column(String(64))  # residential, commercial, etc.
    max_floors_allowed: Mapped[int] = mapped_column(default=1)
    max_footprint_sqm: Mapped[float | None] = mapped_column(default=None)

    applicant_name: Mapped[str] = mapped_column(String(255))

    parcel: Mapped[Parcel] = relationship(back_populates="permits")
