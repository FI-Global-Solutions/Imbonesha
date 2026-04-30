"""Tests for POST /api/v1/detection-jobs/ — DetectionJobViewSet.

Covers:
  - 202 accepted on valid input, job created in QUEUED state
  - 401 when unauthenticated
  - 400 when t1/t2 are the same scene
  - 400 when t1 is captured after t2
  - 404-equivalent (400 validation) when scene IDs don't exist
"""

from __future__ import annotations

import pytest
from datetime import timezone as dt_tz
from unittest.mock import patch

from django.contrib.gis.geos import Polygon
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from detections.models import DetectionJob, JobStatus
from imagery.models import AOI, ImageScene, ImageSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BOUNDARY = Polygon(
    ((30.085, -1.948), (30.095, -1.948), (30.095, -1.940), (30.085, -1.940), (30.085, -1.948)),
    srid=4326,
)


@pytest.fixture()
def aoi(db) -> AOI:
    return AOI.objects.create(name="Test AOI", district="Gasabo", boundary=BOUNDARY)


@pytest.fixture()
def t1_scene(aoi) -> ImageScene:
    return ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2023, 1, 15, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path="test/t1.tif",
    )


@pytest.fixture()
def t2_scene(aoi) -> ImageScene:
    return ImageScene.objects.create(
        aoi=aoi,
        captured_at=timezone.datetime(2024, 3, 20, tzinfo=dt_tz.utc),
        source=ImageSource.PLANET,
        resolution_m=0.5,
        cog_path="test/t2.tif",
    )


@pytest.fixture()
def admin_user(db) -> User:
    return User.objects.create_superuser(
        username="testadmin",
        email="admin@test.local",
        password="testpass",
    )


@pytest.fixture()
def auth_client(admin_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_job_returns_202(auth_client, t1_scene, t2_scene):
    """Valid POST creates a job and returns 202 with job data."""
    with patch("detections.tasks.run_detection_job") as mock_task:
        mock_task.delay.return_value = None
        resp = auth_client.post(
            "/api/v1/detection-jobs/",
            {"t1_scene_id": t1_scene.pk, "t2_scene_id": t2_scene.pk},
            format="json",
        )

    assert resp.status_code == 202, resp.data
    data = resp.json()
    assert data["status"] == JobStatus.QUEUED
    assert data["t1_scene_id"] == t1_scene.pk
    assert data["t2_scene_id"] == t2_scene.pk
    assert DetectionJob.objects.filter(pk=data["id"]).exists()


@pytest.mark.django_db
def test_create_job_unauthenticated_returns_401(db, t1_scene, t2_scene):
    """Unauthenticated request must return 401."""
    client = APIClient()
    resp = client.post(
        "/api/v1/detection-jobs/",
        {"t1_scene_id": t1_scene.pk, "t2_scene_id": t2_scene.pk},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_create_job_same_scene_returns_400(auth_client, t1_scene):
    """t1 == t2 must return 400."""
    resp = auth_client.post(
        "/api/v1/detection-jobs/",
        {"t1_scene_id": t1_scene.pk, "t2_scene_id": t1_scene.pk},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_job_wrong_order_returns_400(auth_client, t1_scene, t2_scene):
    """t1 captured after t2 must return 400."""
    resp = auth_client.post(
        "/api/v1/detection-jobs/",
        {"t1_scene_id": t2_scene.pk, "t2_scene_id": t1_scene.pk},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_job_missing_scene_returns_400(auth_client):
    """Non-existent scene IDs must return 400."""
    resp = auth_client.post(
        "/api/v1/detection-jobs/",
        {"t1_scene_id": 99999, "t2_scene_id": 99998},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_list_jobs(auth_client, t1_scene, t2_scene):
    """GET /api/v1/detection-jobs/ returns a list."""
    DetectionJob.objects.create(
        t1_scene=t1_scene, t2_scene=t2_scene, status=JobStatus.COMPLETED
    )
    resp = auth_client.get("/api/v1/detection-jobs/")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
