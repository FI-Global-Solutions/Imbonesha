"""Seed mock parcels and permits for development and demos.

Generates ~80 parcels covering a small area of Kacyiru sector in Gasabo
district, Kigali. The geographic location is real, the parcels and owners
are entirely fictional.

UPI format: Province/District/Sector/Cell/Parcel
For Kacyiru: 1/01/03/05/XXXX (Province 1=Kigali, District 01=Gasabo,
Sector 03=Kacyiru, Cell 05=Kamatamu — example values).

Scenario distribution:
    60% authorized      — active permit, matches construction
    20% no permit       — primary "flag this" case
    10% expired permit  — permit existed but lapsed
    10% wrong category  — permit for residential, building looks commercial

Run with: python -m app.seed
"""

import asyncio
import logging
import random
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base, Parcel, Permit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Seed for reproducible demos. Bump this if you want a different layout.
random.seed(42)

# --- Geographic anchor ---------------------------------------------------
# Centered on Kacyiru, Kigali. Real coordinates so the demo lines up with
# real maps. Roughly 1 km × 1 km grid of parcels.
ANCHOR_LAT = -1.9441
ANCHOR_LNG = 30.0890

# Grid layout: 10 rows × 8 columns = 80 parcels.
# At Kacyiru's latitude, 1 degree lat ≈ 111 km, 1 degree lng ≈ 111 km.
# We want each parcel ~50m × 50m, so step = 50 / 111000 ≈ 0.00045 degrees.
PARCEL_SIZE_DEG = 0.00045
GRID_ROWS = 10
GRID_COLS = 8

OWNER_NAMES = [
    "Mukamana Jeanne", "Habimana Jean Claude", "Uwimana Marie", "Nshuti Patrick",
    "Mukasine Beatrice", "Bizimana Eric", "Ingabire Diane", "Rwigema Olivier",
    "Umutoni Sandrine", "Kagame Joseph", "Mukantwari Solange", "Ntakirutimana Paul",
    "Niyonsenga Alphonse", "Mukandayisenga Vestine", "Twagirayezu Emmanuel",
    "Uwase Florence", "Hakizimana Theogene", "Murekatete Esperance",
    "Nzeyimana Felix", "Iribagiza Jeanette", "Munyaneza Damascene",
    "Mukamuganga Agathe", "Bazikamwe Innocent", "Uwineza Chantal",
    "Rugamba Aimable", "Mutoni Rachel", "Kanyamibwa David", "Uwizeyimana Patrice",
    "Mukansaga Valerie", "Nshimiyimana Andre",
]


def _random_owner() -> str:
    return random.choice(OWNER_NAMES)


def _generate_upi(row: int, col: int) -> str:
    """Generate a UPI in Rwanda's standard 5-part format."""
    parcel_no = row * GRID_COLS + col + 1
    return f"1/01/03/05/{parcel_no:04d}"


def _parcel_polygon_wkt(row: int, col: int) -> tuple[str, str]:
    """Return (boundary_wkt, centroid_wkt) for a parcel at grid position."""
    # Bottom-left corner of this parcel.
    lng_w = ANCHOR_LNG + col * PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT + row * PARCEL_SIZE_DEG
    lng_e = lng_w + PARCEL_SIZE_DEG
    lat_n = lat_s + PARCEL_SIZE_DEG

    # Polygon coordinates must close (last point = first).
    boundary_wkt = (
        f"SRID=4326;POLYGON(("
        f"{lng_w} {lat_s},"
        f"{lng_e} {lat_s},"
        f"{lng_e} {lat_n},"
        f"{lng_w} {lat_n},"
        f"{lng_w} {lat_s}"
        f"))"
    )
    centroid_wkt = (
        f"SRID=4326;POINT("
        f"{(lng_w + lng_e) / 2} {(lat_s + lat_n) / 2}"
        f")"
    )
    return boundary_wkt, centroid_wkt


def _assign_scenario(parcel_index: int, total: int) -> str:
    """Distribute scenarios across parcels deterministically.

    60% authorized, 20% no_permit, 10% expired, 10% wrong_category.
    """
    rank = parcel_index / total
    if rank < 0.60:
        return "authorized"
    elif rank < 0.80:
        return "no_permit"
    elif rank < 0.90:
        return "expired"
    else:
        return "wrong_category"


def _make_permit(upi: str, scenario: str, parcel_index: int) -> Permit | None:
    """Create a permit for the parcel based on its scenario."""
    if scenario == "no_permit":
        return None

    today = date.today()
    permit_no = f"BP-2023-{parcel_index:06d}"

    if scenario == "authorized":
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category=random.choice(["1", "2", "3"]),
            status="active",
            issued_date=today - timedelta(days=random.randint(60, 800)),
            expiry_date=today + timedelta(days=random.randint(180, 720)),
            intended_use="residential",
            max_floors_allowed=random.choice([1, 2, 3]),
            max_footprint_sqm=random.choice([120.0, 150.0, 200.0, 250.0]),
            applicant_name=_random_owner(),
        )

    if scenario == "expired":
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category="1",
            status="expired",
            issued_date=today - timedelta(days=random.randint(800, 1500)),
            expiry_date=today - timedelta(days=random.randint(30, 365)),
            intended_use="residential",
            max_floors_allowed=2,
            max_footprint_sqm=150.0,
            applicant_name=_random_owner(),
        )

    if scenario == "wrong_category":
        # Permit issued for residential but the AI will detect a structure
        # that looks commercial / industrial in the imagery.
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category="1",
            status="active",
            issued_date=today - timedelta(days=random.randint(60, 400)),
            expiry_date=today + timedelta(days=random.randint(180, 720)),
            intended_use="residential",
            max_floors_allowed=1,
            max_footprint_sqm=100.0,
            applicant_name=_random_owner(),
        )

    return None


async def seed() -> None:
    """Drop all tables, recreate them, and load the seed data."""
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        # Drop and recreate to ensure idempotent seeding during dev.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    total_parcels = GRID_ROWS * GRID_COLS
    parcels_created = 0
    permits_created = 0
    scenarios_count = {"authorized": 0, "no_permit": 0, "expired": 0, "wrong_category": 0}

    async with SessionLocal() as session:
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                parcel_index = row * GRID_COLS + col
                upi = _generate_upi(row, col)
                boundary_wkt, centroid_wkt = _parcel_polygon_wkt(row, col)
                scenario = _assign_scenario(parcel_index, total_parcels)
                scenarios_count[scenario] += 1

                # Determine zone type based on scenario for variety.
                zone_type = random.choice([
                    "high_density_residential",
                    "medium_density_residential",
                    "mixed_use",
                ])
                land_use = "residential" if "residential" in zone_type else "mixed_use"

                parcel = Parcel(
                    upi=upi,
                    boundary=boundary_wkt,
                    centroid=centroid_wkt,
                    owner_name=_random_owner(),
                    land_use=land_use,
                    district="Gasabo",
                    sector="Kacyiru",
                    cell="Kamatamu",
                    zone_type=zone_type,
                    max_floors=random.choice([2, 3, 4]),
                )
                session.add(parcel)
                parcels_created += 1

                permit = _make_permit(upi, scenario, parcel_index)
                if permit is not None:
                    session.add(permit)
                    permits_created += 1

        await session.commit()

    logger.info("=" * 60)
    logger.info("Seed complete")
    logger.info("  Parcels created:  %d", parcels_created)
    logger.info("  Permits created:  %d", permits_created)
    logger.info("  Scenario breakdown:")
    for name, count in scenarios_count.items():
        pct = (count / total_parcels) * 100
        logger.info("    %-18s %2d  (%.0f%%)", name, count, pct)
    logger.info("=" * 60)
    logger.info("Try it:")
    logger.info("  curl http://localhost:8001/api/v1/parcels/1/01/03/05/0001")
    logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
