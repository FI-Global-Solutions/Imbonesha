"""Smoke tests for the mock permit service endpoints.

Run with: docker compose run --rm permit-service pytest

These tests assume the seed data has been loaded. They verify each scenario
distribution shows up correctly in API responses.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_parcel_authorized_scenario(client: AsyncClient) -> None:
    """Parcels in the first 60% of the grid have active permits."""
    # Parcel index 0 is in the authorized bucket.
    response = await client.get("/api/v1/parcels/1/01/03/05/0001")
    assert response.status_code == 200
    body = response.json()
    assert body["upi"] == "1/01/03/05/0001"
    assert body["has_active_permit"] is True
    assert len(body["permits"]) == 1
    assert body["permits"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_get_parcel_no_permit_scenario(client: AsyncClient) -> None:
    """Parcels in 60-80% range have no permit at all — primary flag case."""
    # Index 50 (51st parcel) of 80 total = 62.5% → no_permit.
    response = await client.get("/api/v1/parcels/1/01/03/05/0051")
    assert response.status_code == 200
    body = response.json()
    assert body["has_active_permit"] is False
    assert len(body["permits"]) == 0


@pytest.mark.asyncio
async def test_get_parcel_expired_scenario(client: AsyncClient) -> None:
    """Parcels in 80-90% range have expired permits."""
    # Index 70 of 80 = 87.5% → expired.
    response = await client.get("/api/v1/parcels/1/01/03/05/0071")
    assert response.status_code == 200
    body = response.json()
    assert body["has_active_permit"] is False
    assert len(body["permits"]) == 1
    assert body["permits"][0]["status"] == "expired"


@pytest.mark.asyncio
async def test_get_parcel_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/parcels/9/99/99/99/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_lookup_by_coordinates_inside_parcel(client: AsyncClient) -> None:
    """A point inside the seeded grid should resolve to a parcel."""
    # Roughly center of grid (5 rows, 4 cols out from anchor).
    lat = -1.9441 + 5 * 0.00045 + 0.00022
    lng = 30.0890 + 4 * 0.00045 + 0.00022
    response = await client.get(f"/api/v1/parcels-lookup?lat={lat}&lng={lng}")
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["parcel"] is not None


@pytest.mark.asyncio
async def test_lookup_far_from_any_parcel(client: AsyncClient) -> None:
    """A point far from the grid returns found=False."""
    response = await client.get("/api/v1/parcels-lookup?lat=0&lng=0")
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False


@pytest.mark.asyncio
async def test_response_time_header_present(client: AsyncClient) -> None:
    """Verify our middleware injects the response time header."""
    response = await client.get("/api/v1/parcels/1/01/03/05/0001")
    if response.status_code == 200:
        assert "X-Response-Time-Ms" in response.headers
