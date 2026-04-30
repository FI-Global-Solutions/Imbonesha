"""DRF views for the detections app."""

from __future__ import annotations

from rest_framework import mixins, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import DetectionJob, JobStatus
from .serializers import DetectionJobCreateSerializer, DetectionJobSerializer

_ALLOWED_ROLES = {"admin", "district_admin"}


class DetectionJobViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """Create and monitor detection jobs.

    POST /api/v1/detection-jobs/
        Accepts {t1_scene_id, t2_scene_id}.
        Enqueues a Celery task and returns 202 with the new job.
        Requires: authenticated user with role admin or district_admin.

    GET /api/v1/detection-jobs/
        List all jobs (most recent first).

    GET /api/v1/detection-jobs/{id}/
        Retrieve a single job.
    """

    queryset = DetectionJob.objects.select_related(
        "t1_scene__aoi", "t2_scene__aoi"
    ).prefetch_related("detections")
    serializer_class = DetectionJobSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs) -> Response:
        user = request.user
        user_role = getattr(user, "role", None)
        if not (getattr(user, "is_superuser", False) or user_role in _ALLOWED_ROLES):
            raise PermissionDenied("Only admin or district_admin users may create detection jobs.")

        in_ser = DetectionJobCreateSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        data = in_ser.validated_data

        from imagery.models import ImageScene

        t1 = ImageScene.objects.get(pk=data["t1_scene_id"])
        t2 = ImageScene.objects.get(pk=data["t2_scene_id"])

        job = DetectionJob.objects.create(
            t1_scene=t1,
            t2_scene=t2,
            status=JobStatus.QUEUED,
            model_version="siamese-unet-v2",
        )

        # Enqueue async — if Celery is unavailable, caller gets the job in QUEUED
        # state and can retry or trigger manually.
        try:
            from .tasks import run_detection_job
            run_detection_job.delay(t1.pk, t2.pk)
        except Exception:
            pass  # task enqueue failure is non-fatal; job stays QUEUED

        out_ser = DetectionJobSerializer(job, context={"request": request})
        return Response(out_ser.data, status=status.HTTP_202_ACCEPTED)
