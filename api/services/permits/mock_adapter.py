"""MockPermitAdapter — calls the local FastAPI mock service.

Features:
  - Tenacity retry: 3 attempts, exponential backoff (1s, 2s, 4s).
  - 1-hour Django cache keyed by UPI / coordinate pair.
  - Translates HTTP 404 to None rather than raising.
  - Translates HTTP errors and network failures to PermitServiceError.

The mock service injects 300-500ms latency and 5% error rate (see
infra/docker-compose.yml ERROR_RATE env var), so the retry + cache
strategy is exercised even in local development.
"""

import logging
from datetime import date
from typing import Optional

import httpx
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import (
    LookupResult,
    ParcelData,
    PermitData,
    PermitServiceError,
    PermitVerificationService,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_PARCEL = 3600   # 1 hour
_CACHE_TTL_COORDS = 3600   # 1 hour


def _parse_date(value: str | None) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)


def _permit_from_dict(d: dict) -> PermitData:
    return PermitData(
        permit_no=d["permit_no"],
        category=d["category"],
        status=d["status"],
        intended_use=d["intended_use"],
        max_floors_allowed=d["max_floors_allowed"],
        applicant_name=d["applicant_name"],
        issued_date=_parse_date(d.get("issued_date")),
        expiry_date=_parse_date(d.get("expiry_date")),
        max_footprint_sqm=d.get("max_footprint_sqm"),
    )


def _parcel_from_dict(d: dict) -> ParcelData:
    return ParcelData(
        upi=d["upi"],
        owner_name=d["owner_name"],
        district=d["district"],
        sector=d["sector"],
        cell=d["cell"],
        land_use=d["land_use"],
        zone_type=d["zone_type"],
        centroid_lat=d["centroid_lat"],
        centroid_lng=d["centroid_lng"],
        boundary_geojson=d["boundary_geojson"],
        has_active_permit=d["has_active_permit"],
        permits=[_permit_from_dict(p) for p in d.get("permits", [])],
        max_floors_allowed_by_zone=d.get("max_floors_allowed_by_zone"),
    )


class MockPermitAdapter(PermitVerificationService):
    """Calls the local FastAPI mock of the KUBAKA permit API.

    Args:
        base_url: Base URL of the mock service. Defaults to the
            PERMIT_SERVICE_URL Django setting.
        timeout: HTTP timeout in seconds.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        if base_url is None:
            from django.conf import settings
            base_url = settings.PERMIT_SERVICE_URL
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def verify_upi(self, upi: str) -> Optional[ParcelData]:
        cache_key = f"permit:upi:{upi}"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for UPI %s", upi)
            return cached if cached != "__not_found__" else None

        result = self._fetch_upi(upi)
        if result is None:
            # Cache the 404 too — prevents hammering the service for unknown UPIs.
            cache.set(cache_key, "__not_found__", _CACHE_TTL_PARCEL)
        else:
            cache.set(cache_key, result, _CACHE_TTL_PARCEL)
        return result

    def lookup_by_coords(
        self,
        lat: float,
        lng: float,
        max_distance_m: float = 100.0,
    ) -> LookupResult:
        cache_key = f"permit:coords:{lat:.6f}:{lng:.6f}:{max_distance_m:.0f}"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for coords (%s, %s)", lat, lng)
            return cached

        result = self._fetch_by_coords(lat, lng, max_distance_m)
        cache.set(cache_key, result, _CACHE_TTL_COORDS)
        return result

    # ------------------------------------------------------------------
    # Internal helpers with retry
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=False,
    )
    def _fetch_upi(self, upi: str) -> Optional[ParcelData]:
        """Fetch a parcel by UPI; returns None on 404."""
        url = f"{self._base_url}/api/v1/parcels/{upi}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return _parcel_from_dict(resp.json())
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s fetching UPI %s: %s", exc.response.status_code, upi, exc)
            raise PermitServiceError(f"HTTP {exc.response.status_code} for UPI {upi}") from exc
        except httpx.HTTPError as exc:
            logger.warning("Network error fetching UPI %s: %s", upi, exc)
            raise  # Let tenacity retry on network errors.

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=False,
    )
    def _fetch_by_coords(
        self, lat: float, lng: float, max_distance_m: float
    ) -> LookupResult:
        """Fetch a parcel by coordinates."""
        url = f"{self._base_url}/api/v1/parcels-lookup"
        params = {"lat": lat, "lng": lng, "max_distance_m": max_distance_m}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("found"):
                return LookupResult(found=False)
            return LookupResult(
                found=True,
                parcel=_parcel_from_dict(data["parcel"]),
                distance_m=data.get("distance_m"),
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s for coords (%s, %s): %s", exc.response.status_code, lat, lng, exc)
            raise PermitServiceError(f"HTTP {exc.response.status_code} for coord lookup") from exc
        except httpx.HTTPError as exc:
            logger.warning("Network error for coord lookup (%s, %s): %s", lat, lng, exc)
            raise
