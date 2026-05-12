"""Tests for the notifications app.

Covers:
  - ConsoleBackend.send — returns True, logs correctly
  - ConsoleBackend.backend_name
  - SendGridEmailBackend.send — success (202 status)
  - SendGridEmailBackend.send — failure (exception) returns False
  - SendGridEmailBackend.backend_name
  - _parcel_context — returns parcel fields when parcel exists
  - _parcel_context — returns safe defaults when parcel is None
  - NotificationService.notify_flag_assigned — enqueues task to inspector
  - NotificationService.notify_flag_assigned — subject contains parcel UPI
  - NotificationService.notify_inspection_complete — enqueues task to assigner
  - NotificationService.notify_inspection_complete — skips when no assigner
  - send_notification_task — creates NotificationLog on success
  - send_notification_task — creates NotificationLog on failure
  - send_notification_task — returns early when recipient not found
  - Integration: assign endpoint → notify_flag_assigned called
  - Integration: bulk_assign endpoint → notify_flag_assigned called N times
  - Integration: inspect endpoint → notify_inspection_complete called
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from accounts.models import User, UserRole
from detections.models import ChangeType, Detection, DetectionJob, JobStatus
from flags.models import Flag, FlagStatus, Inspection, InspectionVerdict, Severity
from imagery.models import AOI, ImageScene, ImageSource
from notifications.backends.console import ConsoleBackend
from notifications.models import NotificationLog
from notifications.services import NotificationService, _parcel_context
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
        username="admin_notif",
        email="admin_notif@imbonesha.gov.rw",
        password="pass",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def inspector_user(db):
    return User.objects.create_user(
        username="inspector_notif",
        email="inspector_notif@imbonesha.gov.rw",
        password="pass",
        role=UserRole.INSPECTOR,
        district="Kacyiru",
    )


@pytest.fixture
def parcel(db):
    return Parcel.objects.create(
        upi="1/01/99/00/0001",
        owner_name="Test Owner",
        boundary=SMALL_POLY,
        centroid=KIGALI,
        district="Kacyiru",
        sector="Kacyiru",
        cell="Kamatamu",
        zone_type="residential",
        land_use=LandUse.RESIDENTIAL,
    )


@pytest.fixture
def detection_job(db, parcel):
    aoi = AOI.objects.create(name="Notif Test AOI", boundary=AOI_POLY)
    t1 = ImageScene.objects.create(
        aoi=aoi,
        source=ImageSource.PLANET,
        captured_at=timezone.now() - timedelta(days=30),
        cog_path="test/t1.tif",
        resolution_m=2.0,
    )
    t2 = ImageScene.objects.create(
        aoi=aoi,
        source=ImageSource.PLANET,
        captured_at=timezone.now(),
        cog_path="test/t2.tif",
        resolution_m=2.0,
    )
    return DetectionJob.objects.create(
        t1_scene=t1,
        t2_scene=t2,
        status=JobStatus.COMPLETED,
        model_version="siamese-unet-v3",
        started_at=timezone.now(),
    )


@pytest.fixture
def flag(db, parcel, detection_job):
    det = Detection.objects.create(
        job=detection_job,
        footprint=SMALL_POLY,
        footprint_hash="abc123notif",
        confidence=0.9,
        change_type=ChangeType.NEW_BUILDING,
        area_sqm=250.0,
        parcel=parcel,
    )
    return Flag.objects.create(
        detection=det,
        severity=Severity.HIGH,
        status=FlagStatus.PENDING,
        district="Kacyiru",
    )


@pytest.fixture
def assigned_flag(flag, inspector_user, admin_user):
    flag.assigned_to = inspector_user
    flag.assigned_by = admin_user
    flag.assigned_at = timezone.now()
    flag.status = FlagStatus.ASSIGNED
    flag.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "status"])
    return flag


# ---------------------------------------------------------------------------
# ConsoleBackend
# ---------------------------------------------------------------------------

class TestConsoleBackend:
    def test_send_returns_true(self, db, inspector_user):
        result = ConsoleBackend().send(
            recipient=inspector_user,
            subject="Test subject",
            body_text="Hello",
            body_html="<p>Hello</p>",
        )
        assert result is True

    def test_backend_name(self):
        assert ConsoleBackend().backend_name() == "console"

    def test_send_logs(self, db, inspector_user, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="notifications.backends.console"):
            ConsoleBackend().send(
                recipient=inspector_user,
                subject="Badge test",
                body_text="Body text",
                body_html="<p>Body</p>",
            )
        assert "Badge test" in caplog.text


# ---------------------------------------------------------------------------
# SendGridEmailBackend
# ---------------------------------------------------------------------------

class TestSendGridEmailBackend:
    def _make_backend(self, settings):
        settings.SENDGRID_API_KEY = "SG.fake"
        settings.NOTIFICATION_FROM_EMAIL = "noreply@imbonesha.gov.rw"
        # sendgrid.SendGridAPIClient is imported inside __init__ — patch it there
        with patch("sendgrid.SendGridAPIClient"):
            from notifications.backends.email import SendGridEmailBackend
            return SendGridEmailBackend()

    def test_send_success(self, db, inspector_user, settings):
        backend = self._make_backend(settings)
        mock_response = MagicMock()
        mock_response.status_code = 202
        backend._client = MagicMock()
        backend._client.send.return_value = mock_response

        result = backend.send(
            recipient=inspector_user,
            subject="Test",
            body_text="Body",
            body_html="<p>Body</p>",
        )

        assert result is True
        backend._client.send.assert_called_once()

    def test_send_failure_returns_false(self, db, inspector_user, settings):
        backend = self._make_backend(settings)
        backend._client = MagicMock()
        backend._client.send.side_effect = Exception("Network error")

        result = backend.send(
            recipient=inspector_user,
            subject="Test",
            body_text="Body",
            body_html="<p>Body</p>",
        )

        assert result is False

    def test_backend_name(self, settings):
        backend = self._make_backend(settings)
        assert backend.backend_name() == "sendgrid_email"


# ---------------------------------------------------------------------------
# _parcel_context helper
# ---------------------------------------------------------------------------

class TestParcelContext:
    def test_with_parcel(self, db, flag, parcel):
        ctx = _parcel_context(flag)
        assert ctx["upi"] == parcel.upi
        assert ctx["owner_name"] == parcel.owner_name
        assert ctx["district"] == parcel.district
        assert ctx["sector"] == parcel.sector
        assert ctx["cell"] == parcel.cell
        assert isinstance(ctx["has_active_permit"], bool)

    def test_with_no_parcel(self, db, flag):
        flag.detection.parcel = None
        flag.detection.save(update_fields=["parcel"])
        ctx = _parcel_context(flag)
        assert ctx["upi"] == "Unregistered parcel"
        assert ctx["owner_name"] == "Unknown"
        assert ctx["district"] == "Unknown"
        assert ctx["has_active_permit"] is False


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------

class TestNotificationService:
    def test_notify_flag_assigned_enqueues_task(self, db, flag, inspector_user, admin_user, settings):
        settings.FRONTEND_URL = "http://localhost:54112"
        with patch("notifications.tasks.send_notification_task.delay") as mock_delay:
            NotificationService.notify_flag_assigned(flag, inspector_user, admin_user)
        mock_delay.assert_called_once()
        kwargs = mock_delay.call_args[1]
        assert kwargs["recipient_id"] == str(inspector_user.id)
        assert kwargs["notification_type"] == "flag_assigned"
        assert kwargs["related_flag_id"] == flag.id

    def test_notify_flag_assigned_subject_contains_upi(self, db, flag, inspector_user, admin_user, parcel, settings):
        settings.FRONTEND_URL = "http://localhost:54112"
        with patch("notifications.tasks.send_notification_task.delay") as mock_delay:
            NotificationService.notify_flag_assigned(flag, inspector_user, admin_user)
        subject = mock_delay.call_args[1]["subject"]
        assert parcel.upi in subject

    def test_notify_inspection_complete_enqueues_to_assigner(
        self, db, assigned_flag, inspector_user, admin_user, settings
    ):
        settings.FRONTEND_URL = "http://localhost:54112"
        inspection = Inspection.objects.create(
            flag=assigned_flag,
            inspector=inspector_user,
            verdict=InspectionVerdict.CONFIRMED,
            visited_at=timezone.now(),
        )
        with patch("notifications.tasks.send_notification_task.delay") as mock_delay:
            NotificationService.notify_inspection_complete(assigned_flag, inspection)
        mock_delay.assert_called_once()
        kwargs = mock_delay.call_args[1]
        assert kwargs["recipient_id"] == str(admin_user.id)
        assert kwargs["notification_type"] == "inspection_complete"

    def test_notify_inspection_complete_no_assigner_skips(self, db, flag, inspector_user, settings):
        settings.FRONTEND_URL = "http://localhost:54112"
        inspection = Inspection.objects.create(
            flag=flag,
            inspector=inspector_user,
            verdict=InspectionVerdict.DISMISSED,
            visited_at=timezone.now(),
        )
        with patch("notifications.tasks.send_notification_task.delay") as mock_delay:
            NotificationService.notify_inspection_complete(flag, inspection)
        mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# send_notification_task (called directly, bypassing Celery broker)
# ---------------------------------------------------------------------------

class TestSendNotificationTask:
    """Call the task function directly (no Celery broker) via .run() to bypass bind machinery."""

    def _run_task(self, **kwargs):
        from notifications.tasks import send_notification_task
        return send_notification_task.run(**kwargs)

    def test_creates_log_on_success(self, db, inspector_user):
        with patch("notifications.tasks.get_backend") as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.send.return_value = True
            mock_backend.backend_name.return_value = "console"
            mock_get_backend.return_value = mock_backend

            result = self._run_task(
                recipient_id=str(inspector_user.id),
                subject="Test subject",
                body_text="Body",
                body_html="<p>Body</p>",
                notification_type="flag_assigned",
                related_flag_id=None,
            )

        assert result["success"] is True
        log = NotificationLog.objects.get(recipient=inspector_user)
        assert log.success is True
        assert log.notification_type == "flag_assigned"
        assert log.backend == "console"

    def test_creates_log_on_failure(self, db, inspector_user):
        with patch("notifications.tasks.get_backend") as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.send.return_value = False
            mock_backend.backend_name.return_value = "console"
            mock_get_backend.return_value = mock_backend

            # run() raises the retry exc — catch it so we can inspect the log
            with pytest.raises(Exception):
                self._run_task(
                    recipient_id=str(inspector_user.id),
                    subject="Fail test",
                    body_text="Body",
                    body_html="<p>Body</p>",
                    notification_type="flag_assigned",
                )

        log = NotificationLog.objects.get(recipient=inspector_user)
        assert log.success is False

    def test_missing_recipient_returns_early(self, db):
        with patch("notifications.tasks.get_backend"):
            result = self._run_task(
                recipient_id="999999999",  # non-existent integer PK
                subject="Ghost",
                body_text="Body",
                body_html="<p>Body</p>",
                notification_type="flag_assigned",
            )
        assert result["success"] is False
        assert result["reason"] == "recipient_not_found"
        assert NotificationLog.objects.count() == 0


# ---------------------------------------------------------------------------
# Integration: API endpoints → notification calls
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignEndpointNotification:
    def _token(self, client, email):
        resp = client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": "pass"},
            content_type="application/json",
        )
        return resp.json()["access"]

    def test_assign_enqueues_notification(self, client, flag, inspector_user, admin_user):
        token = self._token(client, admin_user.email)
        with patch("flags.views.NotificationService.notify_flag_assigned") as mock_notify:
            resp = client.post(
                f"/api/v1/flags/{flag.id}/assign/",
                {"inspector_id": inspector_user.id},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
        assert resp.status_code == 200
        assert mock_notify.call_count == 1
        # View calls with keyword args: notify_flag_assigned(flag=..., inspector=..., assigned_by=...)
        call = mock_notify.call_args
        args, kwargs = call.args, call.kwargs
        all_args = list(args) + list(kwargs.values())
        assert inspector_user in all_args
        assert admin_user in all_args

    def test_bulk_assign_enqueues_notification_per_flag(self, client, flag, inspector_user, admin_user):
        # Create a second pending flag sharing the same detection job
        det2 = Detection.objects.create(
            job=flag.detection.job,
            footprint=SMALL_POLY,
            footprint_hash="def456notif",
            confidence=0.8,
            change_type=ChangeType.NEW_BUILDING,
            area_sqm=200.0,
            parcel=flag.detection.parcel,
        )
        flag2 = Flag.objects.create(
            detection=det2,
            severity=Severity.MEDIUM,
            status=FlagStatus.PENDING,
            district="Kacyiru",
        )

        token = self._token(client, admin_user.email)
        with patch("flags.views.NotificationService.notify_flag_assigned") as mock_notify:
            resp = client.post(
                "/api/v1/flags/bulk-assign/",
                {"flag_ids": [str(flag.id), str(flag2.id)], "inspector_id": inspector_user.id},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
        assert resp.status_code == 200
        assert resp.json()["assigned"] == 2
        assert mock_notify.call_count == 2

    def test_inspect_endpoint_notifies_assigner(self, client, assigned_flag, inspector_user):
        from flags.models import InspectionPhoto
        photo = InspectionPhoto.objects.create(
            flag=assigned_flag,
            uploaded_by=inspector_user,
            object_key=f"inspection-photos/{assigned_flag.id}/test.jpg",
            latitude=-1.944,
            longitude=30.089,
            captured_at=timezone.now(),
        )
        token = self._token(client, inspector_user.email)
        with patch("flags.views.NotificationService.notify_inspection_complete") as mock_notify:
            resp = client.post(
                f"/api/v1/flags/{assigned_flag.id}/inspect/",
                {
                    "verdict": "confirmed",
                    "visited_at": timezone.now().isoformat(),
                    "notes": "Confirmed on site",
                    "photo_ids": [str(photo.id)],
                },
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
        assert resp.status_code == 201
        mock_notify.assert_called_once()
        # Unpack positional or keyword args
        call = mock_notify.call_args
        args, kwargs = call.args, call.kwargs
        passed_flag = kwargs.get("flag") or (args[0] if args else None)
        passed_inspection = kwargs.get("inspection") or (args[1] if len(args) > 1 else None)
        assert passed_flag.id == assigned_flag.id
        assert isinstance(passed_inspection, Inspection)
