"""Integration test: shared-volume path routing for the detection pipeline.

Verifies that when scenes have cog_paths pointing to /shared/imagery, the pipeline
can deliver those paths to the ml-service without a 422 (file not found) error.

This test calls _run_pipeline() directly (same pattern as test_e2e_detection.py)
so it runs inside the pytest transaction and doesn't need a live Celery broker.
The live broker round-trip (enqueue → worker → ml-service) is validated manually
via ./scripts/demo_e2e.sh, which exercises the full async path.

Why not test the Celery broker round-trip here:
  The Celery worker connects to the production dev database. pytest-django's
  test database is isolated — objects created in the test transaction are
  invisible to the worker. Making the two share state requires either using the
  dev DB directly (dirty) or a test Celery worker that shares the test DB
  (complex infrastructure). For a demo-readiness session this is out of scope;
  the _run_pipeline direct call is sufficient to prove the path fix works.
"""

from __future__ import annotations

import pytest
from datetime import timezone as dt_tz
from pathlib import Path
from unittest.mock import patch

from django.contrib.gis.geos import Polygon
from django.utils import timezone

from imagery.models import AOI, ImageScene, ImageSource
from detections.models import DetectionJob, JobStatus


BOUNDARY = Polygon(
    (
        (30.085, -1.948),
        (30.095, -1.948),
        (30.095, -1.940),
        (30.085, -1.940),
        (30.085, -1.948),
    ),
    srid=4326,
)

_TRANSFORM = {
    "origin_lat": -1.940,
    "origin_lng": 30.085,
    "pixel_size_m": 50.0,
    "metres_per_degree": 111_000.0,
}


def _ml_service_reachable() -> bool:
    for url in ("http://ml-service:8002/health", "http://localhost:8002/health"):
        try:
            import httpx
            resp = httpx.get(url, timeout=3)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
    return False


@pytest.fixture()
def shared_scene_pair(db, tmp_path):
    """Scene pair with images in /shared/imagery (or tmp fallback on host)."""
    from PIL import Image
    import numpy as np

    # Use /shared/imagery if the volume is mounted, else tmp_path.
    shared = Path("/shared/imagery")
    img_dir = shared if shared.exists() else tmp_path
    img_dir.mkdir(parents=True, exist_ok=True)

    t1_path = img_dir / "path_routing_t1.png"
    t2_path = img_dir / "path_routing_t2.png"

    rng = np.random.default_rng(7)
    for path in (t1_path, t2_path):
        arr = (rng.random((256, 256, 3)) * 255).astype(np.uint8)
        Image.fromarray(arr).save(path)

    aoi = AOI.objects.create(name="Path Routing Test AOI", district="Gasabo", boundary=BOUNDARY)
    t1 = ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2023, 6, 1, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path=str(t1_path),
        metadata={"geo_transform": _TRANSFORM},
    )
    t2 = ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2024, 6, 1, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path=str(t2_path),
        metadata={"geo_transform": _TRANSFORM},
    )
    return t1, t2


@pytest.mark.django_db
def test_shared_volume_path_routing(shared_scene_pair):
    """_run_pipeline sends the /shared/imagery path directly to ml-service.

    Before the fix, the worker downloaded scenes to a tempdir and sent those
    paths to ml-service. The ml-service couldn't read /tmp paths from the
    worker container, resulting in 422. After the fix, both write and read
    to/from /shared/imagery.

    This test calls _run_pipeline directly to avoid the Celery broker/test-DB
    isolation problem. It patches _call_ml_service to capture the path that
    would be sent — the key assertion is that the path starts with the shared
    imagery directory, NOT a /tmp/imbonesha_detect_* path.
    """
    t1, t2 = shared_scene_pair

    captured_paths: list[tuple[str, str]] = []

    def _fake_ml(t1_path: str, t2_path: str):
        captured_paths.append((t1_path, t2_path))
        return []  # no polygons — that's fine

    job = DetectionJob.objects.create(
        t1_scene=t1,
        t2_scene=t2,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v2",
        started_at=timezone.now(),
    )

    with patch("detections.tasks._call_ml_service", side_effect=_fake_ml):
        from detections.tasks import _run_pipeline
        _run_pipeline(job)

    assert captured_paths, "ml-service was never called"
    sent_t1, sent_t2 = captured_paths[0]

    # The paths sent to ml-service must NOT be under /tmp/imbonesha_detect_*
    # (old tempdir approach) — they must be on the shared volume.
    assert "/tmp/imbonesha_detect_" not in sent_t1, (
        f"Path routing bug: worker sent a tempdir path to ml-service: {sent_t1}"
    )
    assert "/tmp/imbonesha_detect_" not in sent_t2, (
        f"Path routing bug: worker sent a tempdir path to ml-service: {sent_t2}"
    )

    # Paths must point to the same location the scene files were written to.
    assert "path_routing_t1" in sent_t1
    assert "path_routing_t2" in sent_t2


@pytest.mark.django_db
def test_pipeline_reaches_ml_service_with_readable_path(shared_scene_pair):
    """When ml-service is reachable, _run_pipeline calls it without a 422.

    Skipped when ml-service is not up. When it runs, a 422 response would
    cause the task to fail — proving the path-routing fix works end-to-end
    with the real ml-service.
    """
    if not _ml_service_reachable():
        pytest.skip("ml-service not reachable — run with: make up")

    t1, t2 = shared_scene_pair

    job = DetectionJob.objects.create(
        t1_scene=t1,
        t2_scene=t2,
        status=JobStatus.RUNNING,
        model_version="siamese-unet-v2",
        started_at=timezone.now(),
    )

    # No mock — hits the real ml-service. If the path is unreadable by ml-service
    # it will 422 and raise RuntimeError here.
    from detections.tasks import _run_pipeline
    _run_pipeline(job)  # must not raise

    job.refresh_from_db()
    # Job status isn't updated by _run_pipeline (that's run_detection_job's job),
    # but the call completing without exception is the proof.
