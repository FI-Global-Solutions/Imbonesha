"""Tests for MobileNotification model and API endpoints.

Covers:
  - MobileNotification created when flag is assigned
  - Unread count returns correct number
  - Mark as read updates is_read and read_at
  - Mark all read updates all unread for current user only
  - Non-authenticated request returns 401
  - Inspector can only see their own notifications
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from accounts.models import User, UserRole
from detections.models import ChangeType, Detection, DetectionJob, JobStatus
from flags.models import Flag, FlagStatus, Severity
from imagery.models import AOI, ImageScene, ImageSource
from notifications.models import MobileNotification
from notifications.services import NotificationService
from parcels.models import LandUse, Parcel


# ---------------------------------------------------------------------------
# Shared geometry
# ---------------------------------------------------------------------------

KIGALI = Point(30.089, -1.944, srid=4326)
SMALL_POLY = Polygon(
    ((30.089, -1.944), (30.090, -1.944), (30.090, -1.945), (30.089, -1.945), (30.089, -1.944)),
    srid=4326,
)
AOI_POLY = Polygon(
    ((30.08, -1.93), (30.10, -1.93), (30.10, -1.95), (30.08, -1.95), (30.08, -1.93)),
    srid=4326,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="mn_admin",
        email="mn_admin@test.rw",
        password="pass",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def inspector1(db):
    return User.objects.create_user(
        username="mn_inspector1",
        email="mn_inspector1@test.rw",
        password="pass",
        role=UserRole.INSPECTOR,
        district="Kacyiru",
    )


@pytest.fixture
def inspector2(db):
    return User.objects.create_user(
        username="mn_inspector2",
        email="mn_inspector2@test.rw",
        password="pass",
        role=UserRole.INSPECTOR,
        district="Nyarugenge",
    )


@pytest.fixture
def parcel(db):
    return Parcel.objects.create(
        upi="1/01/99/00/0099",
        owner_name="MN Test Owner",
        boundary=SMALL_POLY,
        centroid=KIGALI,
        district="Kacyiru",
        sector="Kacyiru",
        cell="Kamatamu",
        zone_type="residential",
        land_use=LandUse.RESIDENTIAL,
    )


@pytest.fixture
def flag(db, parcel):
    aoi = AOI.objects.create(name="MN Test AOI", boundary=AOI_POLY)
    t1 = ImageScene.objects.create(
        aoi=aoi, source=ImageSource.PLANET,
        captured_at=timezone.now() - timedelta(days=30),
        cog_path="test/mn_t1.tif", resolution_m=2.0,
    )
    t2 = ImageScene.objects.create(
        aoi=aoi, source=ImageSource.PLANET,
        captured_at=timezone.now(),
        cog_path="test/mn_t2.tif", resolution_m=2.0,
    )
    job = DetectionJob.objects.create(
        t1_scene=t1, t2_scene=t2, status=JobStatus.COMPLETED,
        model_version="siamese-unet-v3", started_at=timezone.now(),
    )
    det = Detection.objects.create(
        job=job, footprint=SMALL_POLY, footprint_hash=f"mn_{uuid.uuid4().hex}",
        confidence=0.9, change_type=ChangeType.NEW_BUILDING, area_sqm=250.0, parcel=parcel,
    )
    return Flag.objects.create(
        detection=det, severity=Severity.HIGH, status=FlagStatus.PENDING, district="Kacyiru",
    )


def _token(client, email):
    resp = client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": "pass"},
        content_type="application/json",
    )
    return resp.json()["access"]


# ---------------------------------------------------------------------------
# Service: MobileNotification created on flag assignment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMobileNotificationCreated:
    def test_notify_flag_assigned_creates_mobile_notification(
        self, flag, inspector1, admin_user, settings
    ):
        settings.FRONTEND_URL = "http://localhost:54112"
        from unittest.mock import patch
        with patch("notifications.tasks.send_notification_task.delay"):
            NotificationService.notify_flag_assigned(flag, inspector1, admin_user)

        notif = MobileNotification.objects.get(recipient=inspector1)
        assert notif.notification_type == "flag_assigned"
        assert notif.related_flag_id == flag.id
        assert not notif.is_read
        assert notif.read_at is None
        assert str(flag.detection.parcel.upi) in notif.title

    def test_notification_body_contains_severity(self, flag, inspector1, admin_user, settings):
        settings.FRONTEND_URL = "http://localhost:54112"
        from unittest.mock import patch
        with patch("notifications.tasks.send_notification_task.delay"):
            NotificationService.notify_flag_assigned(flag, inspector1, admin_user)

        notif = MobileNotification.objects.get(recipient=inspector1)
        assert "High" in notif.body or "high" in notif.body.lower()


# ---------------------------------------------------------------------------
# API: /notifications/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNotificationListView:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/notifications/")
        assert resp.status_code == 401

    def test_returns_own_notifications(self, client, inspector1, inspector2, flag):
        MobileNotification.objects.create(
            recipient=inspector1, title="For 1", body="body", notification_type="flag_assigned",
        )
        MobileNotification.objects.create(
            recipient=inspector2, title="For 2", body="body", notification_type="flag_assigned",
        )
        token = _token(client, inspector1.email)
        resp = client.get("/api/v1/notifications/", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["title"] == "For 1"

    def test_unread_only_filter(self, client, inspector1):
        MobileNotification.objects.create(
            recipient=inspector1, title="Unread", body="b", notification_type="flag_assigned",
        )
        MobileNotification.objects.create(
            recipient=inspector1, title="Read", body="b", notification_type="flag_assigned",
            is_read=True, read_at=timezone.now(),
        )
        token = _token(client, inspector1.email)
        resp = client.get(
            "/api/v1/notifications/?unread_only=true", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["title"] == "Unread"


# ---------------------------------------------------------------------------
# API: /notifications/unread-count/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUnreadCountView:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/notifications/unread-count/")
        assert resp.status_code == 401

    def test_returns_correct_count(self, client, inspector1, inspector2):
        MobileNotification.objects.create(
            recipient=inspector1, title="A", body="b", notification_type="flag_assigned",
        )
        MobileNotification.objects.create(
            recipient=inspector1, title="B", body="b", notification_type="flag_assigned",
        )
        MobileNotification.objects.create(
            recipient=inspector1, title="C", body="b", notification_type="flag_assigned",
            is_read=True, read_at=timezone.now(),
        )
        # inspector2's notification must NOT be counted
        MobileNotification.objects.create(
            recipient=inspector2, title="D", body="b", notification_type="flag_assigned",
        )
        token = _token(client, inspector1.email)
        resp = client.get("/api/v1/notifications/unread-count/", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2


# ---------------------------------------------------------------------------
# API: /notifications/{id}/read/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkReadView:
    def test_requires_auth(self, client):
        fake_id = uuid.uuid4()
        resp = client.patch(f"/api/v1/notifications/{fake_id}/read/")
        assert resp.status_code == 401

    def test_marks_notification_read(self, client, inspector1):
        notif = MobileNotification.objects.create(
            recipient=inspector1, title="X", body="b", notification_type="flag_assigned",
        )
        token = _token(client, inspector1.email)
        resp = client.patch(
            f"/api/v1/notifications/{notif.id}/read/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

    def test_cannot_mark_other_inspectors_notification(self, client, inspector1, inspector2):
        notif = MobileNotification.objects.create(
            recipient=inspector2, title="Y", body="b", notification_type="flag_assigned",
        )
        token = _token(client, inspector1.email)
        resp = client.patch(
            f"/api/v1/notifications/{notif.id}/read/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 404

    def test_idempotent_if_already_read(self, client, inspector1):
        read_at = timezone.now() - timedelta(hours=1)
        notif = MobileNotification.objects.create(
            recipient=inspector1, title="Z", body="b", notification_type="flag_assigned",
            is_read=True, read_at=read_at,
        )
        token = _token(client, inspector1.email)
        resp = client.patch(
            f"/api/v1/notifications/{notif.id}/read/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        notif.refresh_from_db()
        # read_at should not be updated again
        assert abs((notif.read_at - read_at).total_seconds()) < 1


# ---------------------------------------------------------------------------
# API: /notifications/mark-all-read/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkAllReadView:
    def test_requires_auth(self, client):
        resp = client.post("/api/v1/notifications/mark-all-read/")
        assert resp.status_code == 401

    def test_marks_all_unread_for_user(self, client, inspector1):
        for i in range(3):
            MobileNotification.objects.create(
                recipient=inspector1, title=f"N{i}", body="b", notification_type="flag_assigned",
            )
        token = _token(client, inspector1.email)
        resp = client.post(
            "/api/v1/notifications/mark-all-read/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        assert resp.json()["marked"] == 3
        assert MobileNotification.objects.filter(recipient=inspector1, is_read=False).count() == 0

    def test_does_not_affect_other_users(self, client, inspector1, inspector2):
        MobileNotification.objects.create(
            recipient=inspector1, title="Mine", body="b", notification_type="flag_assigned",
        )
        notif2 = MobileNotification.objects.create(
            recipient=inspector2, title="Theirs", body="b", notification_type="flag_assigned",
        )
        token = _token(client, inspector1.email)
        client.post(
            "/api/v1/notifications/mark-all-read/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        notif2.refresh_from_db()
        assert notif2.is_read is False


# ---------------------------------------------------------------------------
# Push token endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPushTokenView:
    def test_requires_auth(self, client):
        resp = client.post(
            "/api/v1/me/push-token/",
            {"token": "ExponentPushToken[xxx]"},
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_registers_token(self, client, inspector1):
        token = _token(client, inspector1.email)
        resp = client.post(
            "/api/v1/me/push-token/",
            {"token": "ExponentPushToken[abc123]"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        assert resp.json()["registered"] is True
        inspector1.refresh_from_db()
        assert inspector1.expo_push_token == "ExponentPushToken[abc123]"

    def test_unregisters_token(self, client, inspector1):
        inspector1.expo_push_token = "ExponentPushToken[abc123]"
        inspector1.save(update_fields=["expo_push_token"])

        token = _token(client, inspector1.email)
        resp = client.delete(
            "/api/v1/me/push-token/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        assert resp.json()["registered"] is False
        inspector1.refresh_from_db()
        assert inspector1.expo_push_token == ""

    def test_empty_token_returns_400(self, client, inspector1):
        token = _token(client, inspector1.email)
        resp = client.post(
            "/api/v1/me/push-token/",
            {"token": "   "},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# ExpoPushBackend
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestExpoPushBackend:
    def _make_inspector_with_token(self, db):
        user = User.objects.create_user(
            username="push_inspector",
            email="push_inspector@test.rw",
            password="pass",
            role=UserRole.INSPECTOR,
        )
        user.expo_push_token = "ExponentPushToken[test_device]"
        user.save(update_fields=["expo_push_token"])
        return user

    def test_send_success(self, db):
        from unittest.mock import MagicMock, patch
        from notifications.backends.expo_push import ExpoPushBackend

        user = self._make_inspector_with_token(db)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"status": "ok"}]}
        mock_resp.raise_for_status.return_value = None

        with patch("notifications.backends.expo_push.httpx.post", return_value=mock_resp):
            result = ExpoPushBackend().send(
                recipient=user,
                subject="New assignment",
                body_text="High severity",
                body_html="",
                context={"flag_id": 42},
            )
        assert result is True

    def test_send_no_token_returns_false(self, db):
        from notifications.backends.expo_push import ExpoPushBackend

        user = User.objects.create_user(
            username="notokenuser",
            email="notokenuser@test.rw",
            password="pass",
            role=UserRole.INSPECTOR,
        )
        result = ExpoPushBackend().send(
            recipient=user,
            subject="Test",
            body_text="Test",
            body_html="",
        )
        assert result is False

    def test_device_not_registered_clears_token(self, db):
        from unittest.mock import MagicMock, patch
        from notifications.backends.expo_push import ExpoPushBackend

        user = self._make_inspector_with_token(db)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}, "message": "stale"}]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("notifications.backends.expo_push.httpx.post", return_value=mock_resp):
            result = ExpoPushBackend().send(
                recipient=user,
                subject="Test",
                body_text="Test",
                body_html="",
            )
        assert result is False
        user.refresh_from_db()
        assert user.expo_push_token == ""

    def test_push_failure_does_not_retry(self, db, inspector1, settings):
        """Push task with backend_override='expo_push' returns False without raising retry."""
        from unittest.mock import patch
        from notifications.tasks import send_notification_task

        inspector1.expo_push_token = "ExponentPushToken[x]"
        inspector1.save(update_fields=["expo_push_token"])

        with patch("notifications.backends.expo_push.httpx.post", side_effect=Exception("offline")):
            result = send_notification_task.run(
                recipient_id=str(inspector1.id),
                subject="Test",
                body_text="Test",
                body_html="",
                notification_type="flag_assigned",
                backend_override="expo_push",
            )
        assert result["success"] is False
        assert result["reason"] == "push_failed"
