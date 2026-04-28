"""Test fixtures for the permit service.

Uses an in-memory SQLite + spatialite would be ideal, but PostGIS-specific
SQL means we instead spin up against the dev postgres database. Tests must
be run inside docker-compose.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
