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

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base, Parcel, Permit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Seed for reproducible demos. Bump this if you want a different layout.
random.seed(42)

# --- Geographic anchor ---------------------------------------------------
ANCHOR_LAT = -1.9441
ANCHOR_LNG = 30.0890

PARCEL_SIZE_DEG = 0.00045
GRID_ROWS = 10
GRID_COLS = 8

# --- Owner names ---------------------------------------------------------
# Mix of male and female names common in Rwanda, including compound surnames.
OWNER_NAMES = [
    # Female names
    "Mukamana Jeanne", "Uwimana Marie", "Mukasine Beatrice", "Ingabire Diane",
    "Umutoni Sandrine", "Mukantwari Solange", "Mukandayisenga Vestine",
    "Uwase Florence", "Murekatete Esperance", "Iribagiza Jeanette",
    "Mukamuganga Agathe", "Uwineza Chantal", "Mutoni Rachel",
    "Uwizeyimana Patrice", "Mukansaga Valerie", "Niyonzima Claudette",
    "Umuhoza Annonciata", "Mukagasana Odette", "Ineza Felicite",
    # Male names
    "Habimana Jean Claude", "Nshuti Patrick", "Bizimana Eric",
    "Rwigema Olivier", "Kagame Joseph", "Ntakirutimana Paul",
    "Niyonsenga Alphonse", "Twagirayezu Emmanuel", "Hakizimana Theogene",
    "Nzeyimana Felix", "Munyaneza Damascene", "Bazikamwe Innocent",
    "Rugamba Aimable", "Kanyamibwa David", "Nshimiyimana Andre",
    "Nsengiyumva Celestin", "Habineza Janvier", "Nkurunziza Prosper",
    "Bizimungu Didier", "Tuyisenge Alexis",
    # Compound surnames common in Rwanda
    "Nzabonimana Theophile", "Kayitesi Immaculee", "Uwingabire Donatha",
    "Bizumuremyi Leonidas", "Murindabigwi Sylvestre",
]


def _random_owner() -> str:
    return random.choice(OWNER_NAMES)


def _generate_upi(row: int, col: int) -> str:
    parcel_no = row * GRID_COLS + col + 1
    return f"1/01/03/05/{parcel_no:04d}"


def _parcel_polygon_wkt(row: int, col: int, size_frac: float = 1.0) -> tuple[str, str]:
    """Return (boundary_wkt, centroid_wkt) for a parcel at grid position.

    size_frac varies the parcel size between 0.67 and 1.4 of the base cell
    for realism — real parcels aren't all the same size.
    """
    base = PARCEL_SIZE_DEG * size_frac
    lng_w = ANCHOR_LNG + col * PARCEL_SIZE_DEG
    lat_s = ANCHOR_LAT + row * PARCEL_SIZE_DEG
    lng_e = lng_w + base
    lat_n = lat_s + base

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


def _parcel_size_frac(parcel_index: int) -> float:
    """Return a deterministic size multiplier in [0.67, 1.40] for parcel variety."""
    # Five distinct sizes cycling across parcels
    sizes = [0.67, 0.80, 1.00, 1.20, 1.40]
    return sizes[parcel_index % len(sizes)]


def _assign_scenario(parcel_index: int, total: int) -> str:
    rank = parcel_index / total
    if rank < 0.60:
        return "authorized"
    elif rank < 0.80:
        return "no_permit"
    elif rank < 0.90:
        return "expired"
    else:
        return "wrong_category"


def _permit_number(scenario: str, parcel_index: int) -> str:
    """Realistic Rwandan building permit number format: BP/YYYY/MM/NNNNNN."""
    # Vary the year so not all permits look like the same batch.
    years = [2021, 2022, 2023, 2024]
    year = years[parcel_index % len(years)]
    month = (parcel_index % 12) + 1
    return f"BP/{year}/{month:02d}/{parcel_index:06d}"


def _make_permit(upi: str, scenario: str, parcel_index: int) -> Permit | None:
    if scenario == "no_permit":
        return None

    today = date.today()
    permit_no = _permit_number(scenario, parcel_index)

    # 20% of permits: applicant is different from owner (sibling/contractor scenario).
    use_different_applicant = (parcel_index % 5 == 0)
    applicant = _random_owner() if use_different_applicant else _random_owner()

    if scenario == "authorized":
        # Cat 4 (commercial) and Cat 5 (mixed-use) for a small number of parcels.
        if parcel_index % 15 == 0:
            category = "5"   # mixed-use complex
        elif parcel_index % 10 == 0:
            category = "4"   # commercial/industrial
        else:
            category = random.choice(["1", "2", "3"])

        # Issued 2–26 months ago, expires 6–24 months from now.
        issued = today - timedelta(days=random.randint(60, 780))
        expiry = today + timedelta(days=random.randint(180, 720))
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category=category,
            status="active",
            issued_date=issued,
            expiry_date=expiry,
            intended_use="residential" if int(category) <= 3 else "commercial",
            max_floors_allowed=random.choice([1, 2, 3]),
            max_footprint_sqm=random.choice([120.0, 150.0, 200.0, 250.0]),
            applicant_name=applicant,
        )

    if scenario == "expired":
        # Issued 2–4 years ago, expired 1–12 months ago.
        issued = today - timedelta(days=random.randint(800, 1500))
        expiry = today - timedelta(days=random.randint(30, 365))
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category="1",
            status="expired",
            issued_date=issued,
            expiry_date=expiry,
            intended_use="residential",
            max_floors_allowed=2,
            max_footprint_sqm=150.0,
            applicant_name=applicant,
        )

    if scenario == "wrong_category":
        # Residential permit (Cat 1) on a parcel that appears commercial.
        issued = today - timedelta(days=random.randint(60, 400))
        expiry = today + timedelta(days=random.randint(180, 720))
        return Permit(
            id=f"permit-{parcel_index}",
            permit_no=permit_no,
            upi=upi,
            category="1",
            status="active",
            issued_date=issued,
            expiry_date=expiry,
            intended_use="residential",
            max_floors_allowed=1,
            max_footprint_sqm=100.0,
            applicant_name=applicant,
        )

    return None


def _zone_and_land_use(parcel_index: int, scenario: str) -> tuple[str, str]:
    """Return (zone_type, land_use) with realistic variety."""
    # A few green-zone parcels (always critical if flagged)
    if parcel_index in (3, 17, 52):
        return "green_zone", "green_zone"
    # A handful of commercial parcels
    if parcel_index % 13 == 0:
        return "commercial_zone", "commercial"
    # A few mixed-use
    if parcel_index % 9 == 0:
        return "mixed_use", "mixed_use"
    # Rest are residential variants
    zone = random.choice([
        "high_density_residential",
        "medium_density_residential",
        "low_density_residential",
    ])
    return zone, "residential"


async def seed() -> None:
    """Drop all tables, recreate them, and load the seed data."""
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    total_parcels = GRID_ROWS * GRID_COLS
    parcels_created = permits_created = 0
    scenarios_count = {"authorized": 0, "no_permit": 0, "expired": 0, "wrong_category": 0}

    async with SessionLocal() as session:
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                parcel_index = row * GRID_COLS + col
                upi = _generate_upi(row, col)
                size_frac = _parcel_size_frac(parcel_index)
                boundary_wkt, centroid_wkt = _parcel_polygon_wkt(row, col, size_frac)
                scenario = _assign_scenario(parcel_index, total_parcels)
                scenarios_count[scenario] += 1
                zone_type, land_use = _zone_and_land_use(parcel_index, scenario)

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
    logger.info("  curl http://localhost:8015/api/v1/parcels/1/01/03/05/0001")
    logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
