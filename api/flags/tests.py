"""Permission boundary and workflow tests for the flags app.

Tests cover:
  - Role-based queryset filtering (inspector sees only their flags)
  - Assignment permission gates (admin can assign, inspector cannot)
  - Inspection permission gates (inspector can inspect own flag, 403 on others)
  - Bulk-assign endpoint
  - Unassign endpoint
  - Workload endpoint access control
  - State transition guard (can_transition_to)
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from detections.models import Detection, DetectionJob
from imagery.models import AOI, ImageScene
from parcels.models import Parcel

from .models import AuditLog, Flag, FlagStatus, Inspection, Severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_user(email, role, district="Gasabo", **kwargs):
    user = User.objects.create_user(
        email=email,
        username=email,
        password="Test1234!",
        role=role,
        district=district,
        **kwargs,
    )
    return user


_test_aoi = None

def _get_aoi():
    global _test_aoi
    if _test_aoi is None or not AOI.objects.filter(pk=_test_aoi.pk).exists():
        from django.contrib.gis.geos import Polygon as GEOSPolygon
        boundary = GEOSPolygon(
            ((30.05, -1.93), (30.06, -1.93), (30.06, -1.95), (30.05, -1.95), (30.05, -1.93)),
            srid=4326,
        )
        _test_aoi = AOI.objects.create(name="Test AOI", district="Gasabo", boundary=boundary)
    return _test_aoi


def make_flag(parcel=None, status=FlagStatus.PENDING, assigned_to=None):
    """Create a minimal Flag with all required related objects."""
    aoi = _get_aoi()
    scene = ImageScene.objects.create(
        aoi=aoi,
        source="levir",
        resolution_m=0.5,
        cog_path=f"test/scene_{ImageScene.objects.count()}.tif",
        captured_at=timezone.now(),
    )
    job = DetectionJob.objects.create(
        t1_scene=scene,
        t2_scene=scene,
        status="completed",
    )
    if parcel is None:
        from django.contrib.gis.geos import Polygon as GEOSPolygon
        parcel_boundary = GEOSPolygon(
            ((30.058, -1.940), (30.059, -1.940), (30.059, -1.941), (30.058, -1.941), (30.058, -1.940)),
            srid=4326,
        )
        from django.contrib.gis.geos import Point
        parcel = Parcel.objects.create(
            upi=f"1/01/00/00/{Parcel.objects.count():04d}",
            owner_name="Test Owner",
            district="Gasabo",
            sector="Kacyiru",
            cell="Kamatamu",
            boundary=parcel_boundary,
            centroid=Point(30.0585, -1.9405, srid=4326),
        )
    from django.contrib.gis.geos import GEOSGeometry
    footprint = GEOSGeometry(
        '{"type":"Polygon","coordinates":[[[30.058,−1.94],[30.059,−1.94],[30.059,−1.941],[30.058,−1.941],[30.058,−1.94]]]}',
        srid=4326,
    ) if False else None

    # Use a simple WKT polygon
    from django.contrib.gis.geos import Polygon
    footprint = Polygon(
        ((30.058, -1.940), (30.059, -1.940), (30.059, -1.941), (30.058, -1.941), (30.058, -1.940)),
        srid=4326,
    )
    detection = Detection.objects.create(
        job=job,
        parcel=parcel,
        footprint=footprint,
        confidence=0.75,
        area_sqm=120.0,
        change_type="new_building",
        footprint_hash=f"hash_{Detection.objects.count()}",
    )
    flag = Flag.objects.create(
        detection=detection,
        severity=Severity.HIGH,
        status=status,
        assigned_to=assigned_to,
        district="Gasabo",
    )
    return flag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class FlagQuerysetFilteringTest(TestCase):
    """Inspector sees only their own flags; admin sees all."""

    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector1 = make_user("insp1@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.inspector2 = make_user("insp2@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.flag_assigned_to_1 = make_flag(assigned_to=self.inspector1, status=FlagStatus.ASSIGNED)
        self.flag_assigned_to_2 = make_flag(assigned_to=self.inspector2, status=FlagStatus.ASSIGNED)
        self.flag_unassigned = make_flag()
        self.client = APIClient()

    def test_inspector_sees_only_own_flags(self):
        self.client.force_authenticate(self.inspector1)
        resp = self.client.get("/api/v1/flags/")
        self.assertEqual(resp.status_code, 200)
        ids = [f["id"] for f in resp.data["results"]]
        self.assertIn(self.flag_assigned_to_1.id, ids)
        self.assertNotIn(self.flag_assigned_to_2.id, ids)
        self.assertNotIn(self.flag_unassigned.id, ids)

    def test_admin_sees_all_flags(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/v1/flags/")
        self.assertEqual(resp.status_code, 200)
        ids = [f["id"] for f in resp.data["results"]]
        self.assertIn(self.flag_assigned_to_1.id, ids)
        self.assertIn(self.flag_assigned_to_2.id, ids)
        self.assertIn(self.flag_unassigned.id, ids)

    def test_inspector_cannot_retrieve_another_inspectors_flag(self):
        self.client.force_authenticate(self.inspector1)
        resp = self.client.get(f"/api/v1/flags/{self.flag_assigned_to_2.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_gets_401(self):
        resp = self.client.get("/api/v1/flags/")
        self.assertEqual(resp.status_code, 401)


class AssignEndpointTest(TestCase):
    """Admin can assign; inspector cannot assign (even to themselves)."""

    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector = make_user("insp@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.flag = make_flag()
        self.client = APIClient()

    def test_admin_can_assign_flag(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/v1/flags/{self.flag.id}/assign/",
            {"inspector_id": self.inspector.id},
        )
        self.assertEqual(resp.status_code, 200)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, "assigned")
        self.assertEqual(self.flag.assigned_to, self.inspector)
        self.assertEqual(self.flag.assigned_by, self.admin)
        self.assertIsNotNone(self.flag.assigned_at)

    def test_inspector_cannot_assign_flag(self):
        """Inspectors must not be able to assign flags — not even to themselves."""
        self.client.force_authenticate(self.inspector)
        # Inspector needs to see the flag first — make it theirs
        self.flag.assigned_to = self.inspector
        self.flag.status = FlagStatus.ASSIGNED
        self.flag.save()
        resp = self.client.post(
            f"/api/v1/flags/{self.flag.id}/assign/",
            {"inspector_id": self.inspector.id},
        )
        self.assertEqual(resp.status_code, 403)

    def test_assign_creates_audit_log(self):
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/v1/flags/{self.flag.id}/assign/", {"inspector_id": self.inspector.id})
        log = AuditLog.objects.filter(flag=self.flag, event="assigned").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.admin)

    def test_assign_nonexistent_inspector_returns_404(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/assign/", {"inspector_id": 99999})
        self.assertEqual(resp.status_code, 404)

    def test_assign_already_closed_flag_returns_400(self):
        self.flag.status = FlagStatus.CLOSED
        self.flag.save()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/assign/", {"inspector_id": self.inspector.id})
        self.assertEqual(resp.status_code, 400)


class UnassignEndpointTest(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector = make_user("insp@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.flag = make_flag(assigned_to=self.inspector, status=FlagStatus.ASSIGNED)
        self.flag.assigned_by = self.admin
        self.flag.save()
        self.client = APIClient()

    def test_admin_can_unassign(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/unassign/")
        self.assertEqual(resp.status_code, 200)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, "pending")
        self.assertIsNone(self.flag.assigned_to)

    def test_inspector_cannot_unassign(self):
        self.client.force_authenticate(self.inspector)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/unassign/")
        self.assertEqual(resp.status_code, 403)


class BulkAssignEndpointTest(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector = make_user("insp@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.flag1 = make_flag()
        self.flag2 = make_flag()
        self.closed_flag = make_flag(status=FlagStatus.CLOSED)
        self.client = APIClient()

    def test_bulk_assign_assigns_eligible_flags(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/v1/flags/bulk-assign/", {
            "flag_ids": [self.flag1.id, self.flag2.id],
            "inspector_id": self.inspector.id,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["assigned"], 2)
        self.assertEqual(resp.data["skipped"], 0)

    def test_bulk_assign_skips_closed_flags(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/v1/flags/bulk-assign/", {
            "flag_ids": [self.flag1.id, self.closed_flag.id],
            "inspector_id": self.inspector.id,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["assigned"], 1)
        self.assertEqual(resp.data["skipped"], 1)

    def test_inspector_cannot_bulk_assign(self):
        self.client.force_authenticate(self.inspector)
        resp = self.client.post("/api/v1/flags/bulk-assign/", {
            "flag_ids": [self.flag1.id],
            "inspector_id": self.inspector.id,
        }, format="json")
        self.assertEqual(resp.status_code, 403)


class InspectEndpointTest(TestCase):
    """Inspector can submit verdict on their own flag; gets 403 on others'."""

    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector1 = make_user("insp1@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.inspector2 = make_user("insp2@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.flag = make_flag(assigned_to=self.inspector1, status=FlagStatus.ASSIGNED)
        self.client = APIClient()
        self.payload = {
            "verdict": "confirmed",
            "notes": "Large structure, no permit",
            "construction_stage": "roofing",
            "estimated_floors": 2,
            "occupancy_observed": False,
            "visited_at": "2026-05-01T10:00:00Z",
        }

    def test_assigned_inspector_can_submit_inspection(self):
        self.client.force_authenticate(self.inspector1)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", self.payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, "confirmed")
        self.assertEqual(Inspection.objects.filter(flag=self.flag).count(), 1)

    def test_other_inspector_cannot_inspect(self):
        self.client.force_authenticate(self.inspector2)
        # inspector2 can't even see this flag (filtered queryset → 404)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", self.payload, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_admin_can_inspect_any_flag(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", self.payload, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_inspection_creates_audit_log(self):
        self.client.force_authenticate(self.inspector1)
        self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", self.payload, format="json")
        log = AuditLog.objects.filter(flag=self.flag, event="inspection_submitted").first()
        self.assertIsNotNone(log)

    def test_invalid_verdict_returns_400(self):
        self.client.force_authenticate(self.inspector1)
        bad = {**self.payload, "verdict": "needs_review"}
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", bad, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_missing_visited_at_returns_400(self):
        self.client.force_authenticate(self.inspector1)
        bad = {**self.payload}
        del bad["visited_at"]
        resp = self.client.post(f"/api/v1/flags/{self.flag.id}/inspect/", bad, format="json")
        self.assertEqual(resp.status_code, 400)


class WorkloadEndpointTest(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.rw", UserRole.ADMIN, district="")
        self.inspector = make_user("insp@test.rw", UserRole.INSPECTOR, district="Gasabo")
        self.client = APIClient()

    def test_admin_can_view_workload(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/v1/inspectors/workload/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)

    def test_inspector_cannot_view_workload(self):
        self.client.force_authenticate(self.inspector)
        resp = self.client.get("/api/v1/inspectors/workload/")
        self.assertEqual(resp.status_code, 403)


class TransitionGuardTest(TestCase):
    """Unit tests for can_transition_to / transition_to on the Flag model."""

    def setUp(self):
        self.actor = make_user("actor@test.rw", UserRole.ADMIN, district="")
        self.flag = make_flag()

    def test_pending_can_go_to_assigned(self):
        self.assertTrue(self.flag.can_transition_to("assigned"))

    def test_pending_cannot_go_to_closed(self):
        self.assertFalse(self.flag.can_transition_to("closed"))

    def test_closed_has_no_transitions(self):
        self.flag.status = "closed"
        self.flag.save()
        self.assertFalse(self.flag.can_transition_to("confirmed"))
        self.assertFalse(self.flag.can_transition_to("pending"))

    def test_transition_to_raises_on_invalid(self):
        with self.assertRaises(ValueError):
            self.flag.transition_to("closed", self.actor)

    def test_transition_to_updates_status_and_logs(self):
        self.flag.status = "assigned"
        self.flag.save()
        self.flag.transition_to("confirmed", self.actor, message="Test confirm")
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, "confirmed")
        log = AuditLog.objects.filter(flag=self.flag, event="status_changed").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.after["status"], "confirmed")
