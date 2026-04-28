"""Mock permit verification service.

Mirrors the API surface we expect to negotiate with the real KUBAKA platform.
The Imbonesha main API talks to this service through an adapter — to swap
to the real KUBAKA, we implement a different adapter behind the same Python
interface and change one config value.

Endpoints:
    GET  /api/v1/parcels/{upi}                  Lookup parcel by UPI
    GET  /api/v1/parcels/lookup                  Lookup parcel by coordinates
    GET  /api/v1/parcels/{upi}/permits           List permits for a parcel
    GET  /api/v1/permits/{permit_no}             Lookup a specific permit
    GET  /health                                 Health check (no latency)
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.middleware import RealisticConditionsMiddleware
from app.models import Parcel, Permit
from app.schemas import (
    ParcelLookupResponse,
    ParcelResponse,
    PermitResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KUBAKA Mock Permit Service",
    description=(
        "Mock implementation of the Rwanda Housing Authority / KUBAKA permit "
        "verification API. Used during MVP development before real API access "
        "is granted. Response shapes here are the integration contract we will "
        "negotiate with the KUBAKA team."
    ),
    version="0.1.0",
)

app.add_middleware(RealisticConditionsMiddleware)


# --- Helpers --------------------------------------------------------------


def _parcel_to_response(parcel: Parcel) -> ParcelResponse:
    """Convert a Parcel ORM object into the API response shape."""
    from geoalchemy2.shape import to_shape

    boundary_shape = to_shape(parcel.boundary)
    centroid_shape = to_shape(parcel.centroid)

    permits = [
        PermitResponse(
            permit_no=p.permit_no,
            category=p.category,
            status=p.status,
            issued_date=p.issued_date,
            expiry_date=p.expiry_date,
            intended_use=p.intended_use,
            max_floors_allowed=p.max_floors_allowed,
            max_footprint_sqm=p.max_footprint_sqm,
            applicant_name=p.applicant_name,
        )
        for p in parcel.permits
    ]

    today = date.today()
    has_active_permit = any(
        p.status == "active"
        and (p.expiry_date is None or p.expiry_date >= today)
        for p in parcel.permits
    )

    return ParcelResponse(
        upi=parcel.upi,
        owner_name=parcel.owner_name,
        district=parcel.district,
        sector=parcel.sector,
        cell=parcel.cell,
        land_use=parcel.land_use,
        zone_type=parcel.zone_type,
        max_floors_allowed_by_zone=parcel.max_floors,
        centroid_lat=centroid_shape.y,
        centroid_lng=centroid_shape.x,
        boundary_geojson={
            "type": "Polygon",
            "coordinates": [list(boundary_shape.exterior.coords)],
        },
        permits=permits,
        has_active_permit=has_active_permit,
    )


# --- Endpoints ------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """Health check — bypasses latency/error injection."""
    return {"status": "ok", "service": "permit-mock", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/parcels/{upi:path}", response_model=ParcelResponse)
async def get_parcel(
    upi: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ParcelResponse:
    """Lookup a parcel by its UPI.

    UPI uses '/' as separator, so we accept it via path parameter with `:path`
    converter. Example: GET /api/v1/parcels/1/01/03/05/0142
    """
    stmt = (
        select(Parcel)
        .options(selectinload(Parcel.permits))
        .where(Parcel.upi == upi)
    )
    result = await session.execute(stmt)
    parcel = result.scalar_one_or_none()

    if parcel is None:
        raise HTTPException(
            status_code=404,
            detail=f"Parcel with UPI '{upi}' not found in registry",
        )

    return _parcel_to_response(parcel)


@app.get("/api/v1/parcels-lookup", response_model=ParcelLookupResponse)
async def lookup_parcel_by_coords(
    session: Annotated[AsyncSession, Depends(get_session)],
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    max_distance_m: float = Query(100, gt=0, le=10000),
) -> ParcelLookupResponse:
    """Find the parcel containing a given coordinate.

    Returns the parcel whose boundary contains (lat, lng), or — if none
    contains the point — the nearest parcel within `max_distance_m`.

    This endpoint is what Imbonesha calls when the AI detects a new building
    at coordinates and we need to determine which parcel it falls on.
    """
    from sqlalchemy import func as sql_func

    point_wkt = f"SRID=4326;POINT({lng} {lat})"

    # First try: find a parcel whose boundary contains the point.
    contains_stmt = (
        select(Parcel)
        .options(selectinload(Parcel.permits))
        .where(sql_func.ST_Contains(Parcel.boundary, sql_func.ST_GeomFromEWKT(point_wkt)))
        .limit(1)
    )
    result = await session.execute(contains_stmt)
    parcel = result.scalar_one_or_none()

    if parcel is not None:
        return ParcelLookupResponse(
            found=True,
            parcel=_parcel_to_response(parcel),
            distance_m=0.0,
        )

    # Second try: nearest parcel within max_distance_m using geography casts
    # so distance is in meters.
    nearest_stmt = (
        select(
            Parcel,
            sql_func.ST_Distance(
                sql_func.ST_GeogFromWKB(Parcel.centroid),
                sql_func.ST_GeogFromText(f"POINT({lng} {lat})"),
            ).label("dist_m"),
        )
        .options(selectinload(Parcel.permits))
        .order_by("dist_m")
        .limit(1)
    )
    result = await session.execute(nearest_stmt)
    row = result.first()

    if row is None or row.dist_m > max_distance_m:
        return ParcelLookupResponse(found=False)

    return ParcelLookupResponse(
        found=True,
        parcel=_parcel_to_response(row.Parcel),
        distance_m=float(row.dist_m),
    )


@app.get("/api/v1/parcels/{upi:path}/permits", response_model=list[PermitResponse])
async def get_parcel_permits(
    upi: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PermitResponse]:
    """List all permits for a parcel."""
    stmt = select(Permit).where(Permit.upi == upi).order_by(Permit.issued_date.desc())
    result = await session.execute(stmt)
    permits = result.scalars().all()

    if not permits:
        # Verify the parcel itself exists — otherwise this is a 404, not an
        # empty list. This distinction matters for the calling service.
        parcel_stmt = select(Parcel).where(Parcel.upi == upi)
        parcel_result = await session.execute(parcel_stmt)
        if parcel_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Parcel with UPI '{upi}' not found in registry",
            )

    return [
        PermitResponse(
            permit_no=p.permit_no,
            category=p.category,
            status=p.status,
            issued_date=p.issued_date,
            expiry_date=p.expiry_date,
            intended_use=p.intended_use,
            max_floors_allowed=p.max_floors_allowed,
            max_footprint_sqm=p.max_footprint_sqm,
            applicant_name=p.applicant_name,
        )
        for p in permits
    ]


@app.get("/api/v1/permits/{permit_no}", response_model=PermitResponse)
async def get_permit(
    permit_no: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PermitResponse:
    """Lookup a specific permit by its number."""
    stmt = select(Permit).where(Permit.permit_no == permit_no)
    result = await session.execute(stmt)
    permit = result.scalar_one_or_none()

    if permit is None:
        raise HTTPException(
            status_code=404,
            detail=f"Permit '{permit_no}' not found",
        )

    return PermitResponse(
        permit_no=permit.permit_no,
        category=permit.category,
        status=permit.status,
        issued_date=permit.issued_date,
        expiry_date=permit.expiry_date,
        intended_use=permit.intended_use,
        max_floors_allowed=permit.max_floors_allowed,
        max_footprint_sqm=permit.max_footprint_sqm,
        applicant_name=permit.applicant_name,
    )
