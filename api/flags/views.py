"""DRF views for flags app."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import Flag
from .serializers import FlagDetailSerializer, FlagListSerializer


class FlagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["severity", "status", "district"]
    search_fields = ["detection__parcel__upi", "detection__parcel__owner_name", "district"]
    ordering_fields = ["created_at", "severity", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Flag.objects
            .select_related(
                "detection__job__t1_scene",
                "detection__job__t2_scene",
                "detection__parcel",
            )
            .prefetch_related("detection__parcel__permits")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "retrieve" or self.action == "imagery":
            return FlagDetailSerializer
        return FlagListSerializer

    @action(detail=True, methods=["get"], url_path="imagery")
    def imagery(self, request: Request, pk=None) -> Response:
        """Return presigned MinIO URLs for T1 and T2 images (valid 15 min)."""
        flag = self.get_object()
        job = flag.detection.job

        t1_url = _presign(job.t1_scene.cog_path) if job.t1_scene else None
        t2_url = _presign(job.t2_scene.cog_path) if job.t2_scene else None

        return Response({
            "t1_url": t1_url,
            "t2_url": t2_url,
            "t1_captured_at": job.t1_scene.captured_at if job.t1_scene else None,
            "t2_captured_at": job.t2_scene.captured_at if job.t2_scene else None,
        })


def _presign(cog_path: str) -> str | None:
    """Generate a 15-minute presigned GET URL for a MinIO object.

    MinIO is configured with MINIO_SERVER_URL=http://localhost:9007 so it
    produces presigned URLs using localhost:9007 — valid from the browser.
    The api container still connects to MinIO via the internal minio:9000
    hostname for uploads and signing requests.
    """
    if not cog_path:
        return None
    try:
        from minio import Minio

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=getattr(settings, "MINIO_SECURE", False),
        )
        bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
        return client.presigned_get_object(bucket, cog_path, expires=timedelta(minutes=15))
    except Exception:
        return None
