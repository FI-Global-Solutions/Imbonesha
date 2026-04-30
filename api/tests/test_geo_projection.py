"""Unit tests for the pixel → WGS84 projection helper in detections/tasks.py.

Key invariant tested: image row 0 is the TOP (north) of the image, so
increasing row should decrease latitude, not increase it.

All tests use proper closed polygon rings (≥4 points) because Django's
GEOS backend requires at least 4 points for a valid LinearRing.
"""

from __future__ import annotations

import pytest

from detections.tasks import _pixel_polygon_to_wgs84


# A 1-pixel-per-metre transform anchored at a known Kacyiru corner.
_TRANSFORM = {
    "origin_lng": 30.089,
    "origin_lat": -1.944,
    "pixel_size_m": 1.0,
    "metres_per_degree": 111_000.0,
}

# 1 px = 1/111_000 degrees ≈ 9.009e-6 degrees
_DEG_PER_PX = 1.0 / 111_000.0


def _rect(col0, row0, col1, row1):
    """Return a closed 5-point polygon ring for a rectangle in pixel coords."""
    return [
        (col0, row0), (col1, row0), (col1, row1), (col0, row1), (col0, row0)
    ]


def _unit_rect_at(col, row):
    """1-pixel closed ring with top-left at (col, row)."""
    return _rect(col, row, col + 1, row + 1)


def test_row0_is_northern_edge():
    """Polygon starting at pixel row=0 must have its top at origin_lat."""
    # Ring: top-left (col=0, row=0) — this vertex maps to (origin_lng, origin_lat)
    coords = _unit_rect_at(0, 0)
    poly = _pixel_polygon_to_wgs84(coords, _TRANSFORM)
    ring = poly[0]  # exterior ring; first point is (col=0, row=0)
    lng, lat = ring[0][0], ring[0][1]

    assert abs(lng - _TRANSFORM["origin_lng"]) < 1e-9
    assert abs(lat - _TRANSFORM["origin_lat"]) < 1e-9


def test_increasing_row_decreases_latitude():
    """Moving down the image (increasing row) must decrease latitude."""
    top_coords = _unit_rect_at(0, 0)
    bot_coords = _unit_rect_at(0, 100)

    lat_top = _pixel_polygon_to_wgs84(top_coords, _TRANSFORM)[0][0][1]
    lat_bot = _pixel_polygon_to_wgs84(bot_coords, _TRANSFORM)[0][0][1]

    assert lat_top > lat_bot, (
        f"row=0 lat={lat_top:.8f} should be NORTH of row=100 lat={lat_bot:.8f}"
    )


def test_increasing_col_increases_longitude():
    """Moving right across the image (increasing col) must increase longitude."""
    left_coords = _unit_rect_at(0, 0)
    right_coords = _unit_rect_at(100, 0)

    lng_left = _pixel_polygon_to_wgs84(left_coords, _TRANSFORM)[0][0][0]
    lng_right = _pixel_polygon_to_wgs84(right_coords, _TRANSFORM)[0][0][0]

    assert lng_right > lng_left, (
        f"col=100 lng={lng_right:.8f} should be EAST of col=0 lng={lng_left:.8f}"
    )


def test_pixel_displacement_magnitude():
    """100-pixel displacement at 1 m/px shifts coords by 100/111_000 degrees."""
    coords = _unit_rect_at(100, 100)
    poly = _pixel_polygon_to_wgs84(coords, _TRANSFORM)
    lng, lat = poly[0][0][0], poly[0][0][1]

    expected_lng = _TRANSFORM["origin_lng"] + 100 * _DEG_PER_PX
    expected_lat = _TRANSFORM["origin_lat"] - 100 * _DEG_PER_PX  # row subtracts

    assert abs(lng - expected_lng) < 1e-9, f"lng mismatch: {lng} vs {expected_lng}"
    assert abs(lat - expected_lat) < 1e-9, f"lat mismatch: {lat} vs {expected_lat}"


def test_fallback_transform_north_west_origin():
    """With transform=None, row=0 coords are north of row=50 coords."""
    top_coords = _unit_rect_at(0, 0)
    bot_coords = _unit_rect_at(0, 50)

    lat_top = _pixel_polygon_to_wgs84(top_coords, None)[0][0][1]
    lat_bot = _pixel_polygon_to_wgs84(bot_coords, None)[0][0][1]

    assert lat_top > lat_bot, (
        f"Fallback: row=0 lat={lat_top:.8f} should be NORTH of row=50 lat={lat_bot:.8f}"
    )


def test_polygon_ring_closes():
    """Returned polygon must be a valid closed ring (first pt == last pt)."""
    coords = _rect(10, 20, 50, 60)
    poly = _pixel_polygon_to_wgs84(coords, _TRANSFORM)
    ring = poly[0]  # exterior ring
    assert ring[0] == ring[-1], "Polygon ring must be closed"
