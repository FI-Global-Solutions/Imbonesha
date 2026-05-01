"""DRF views for flags app."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .filters import FlagFilter
from .models import Flag
from .serializers import FlagDetailSerializer, FlagListSerializer


class FlagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_class = FlagFilter
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
        """Return stream URLs for T1 and T2 images via the /stream/ action."""
        flag = self.get_object()
        job = flag.detection.job

        base = request.build_absolute_uri(f"/api/v1/flags/{flag.id}/")

        def stream_url(scene, which: str):
            if not scene:
                return None
            return f"{base}stream/?t={which}"

        return Response({
            "t1_url": stream_url(job.t1_scene, "t1"),
            "t2_url": stream_url(job.t2_scene, "t2"),
            "t1_captured_at": job.t1_scene.captured_at if job.t1_scene else None,
            "t2_captured_at": job.t2_scene.captured_at if job.t2_scene else None,
        })

    @action(detail=True, methods=["get"], url_path="stream",
            permission_classes=[AllowAny])
    def stream(self, request: Request, pk=None) -> StreamingHttpResponse:
        """Stream a T1 or T2 image directly from MinIO to the browser.

        Accepts JWT via Authorization header OR ?token= query param so that
        plain <img> tags (which can't set headers) can load images.
        """
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import TokenError

        # Authenticate: prefer Authorization header, fall back to ?token=
        user = request.user if request.user and request.user.is_authenticated else None
        if not user:
            raw = request.query_params.get("token")
            if not raw:
                return StreamingHttpResponse(status=401)
            try:
                jwt_auth = JWTAuthentication()
                validated = jwt_auth.get_validated_token(raw)
                user = jwt_auth.get_user(validated)
            except (TokenError, Exception):
                return StreamingHttpResponse(status=401)
        if not user or not user.is_authenticated:
            return StreamingHttpResponse(status=401)

        # Ensure get_object sees an authenticated user (needed for queryset)
        request._request.user = user
        flag = self.get_object()
        job = flag.detection.job
        which = request.query_params.get("t", "t1")
        scene = job.t1_scene if which == "t1" else job.t2_scene

        if not scene or not scene.cog_path:
            return StreamingHttpResponse(status=404)

        try:
            from minio import Minio

            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=getattr(settings, "MINIO_SECURE", False),
            )
            bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
            resp = client.get_object(bucket, scene.cog_path)
            return StreamingHttpResponse(
                resp.stream(amt=65536),
                content_type=resp.headers.get("Content-Type", "image/png"),
                headers={"Cache-Control": "private, max-age=3600"},
            )
        except Exception:
            return StreamingHttpResponse(status=502)


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
