"""DRF views for flags app."""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from .filters import FlagFilter
from .models import Flag, Report
from .serializers import FlagDetailSerializer, FlagListSerializer, ReportSerializer

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-process cache for cropped+annotated tiles.
# Keyed by (flag_id, which).  Values are raw PNG bytes.
# Safe because crop+overlay is fully deterministic per flag.
# ---------------------------------------------------------------------------
_tile_cache: dict[tuple[int, str], bytes] = {}

_PAD = 64          # pixels of padding around the detection footprint
_MIN_SIZE = 256    # minimum crop dimension (px)
_MAX_SIZE = 512    # maximum crop dimension (px)
_IMG_SIZE = 1024   # source image is always 1024×1024

# Polygon overlay colours (R, G, B, A)
_FILL_COLOUR = (220, 38, 38, 90)    # red-600 @ ~35% alpha
_STROKE_COLOUR = (220, 38, 38, 255) # solid red-600


def _crop_box(
    footprint,                      # django.contrib.gis.geos.Polygon (WGS84)
    transform: dict,                # scene metadata geo_transform dict
) -> tuple[int, int, int, int]:
    """Return (left, upper, right, lower) pixel crop box for the detection footprint.

    Coordinate-space chain (forward):
        WGS84 (lng, lat)  →  pixel (col, row)
        col = (lng - origin_lng) / deg_per_pixel
        row = (origin_lat - lat) / deg_per_pixel   ← lat decreases as row increases

    Inverse is trivial since the transform is a simple scale+offset.

    The box is padded by _PAD, expanded to _MIN_SIZE, clipped to _MAX_SIZE,
    and clamped to [0, _IMG_SIZE].  Same box is used for T1 and T2 so the
    swipe slider aligns perfectly.
    """
    origin_lng = transform["origin_lng"]
    origin_lat = transform["origin_lat"]
    pixel_size_m = transform["pixel_size_m"]
    m_per_deg = transform.get("metres_per_degree", 111_000.0)
    deg_per_pixel = pixel_size_m / m_per_deg

    # Footprint extent: (xmin, ymin, xmax, ymax) = (lng_min, lat_min, lng_max, lat_max)
    ext = footprint.extent
    lng_min, lat_min, lng_max, lat_max = ext

    col_min = int((lng_min - origin_lng) / deg_per_pixel)
    col_max = int((lng_max - origin_lng) / deg_per_pixel)
    row_min = int((origin_lat - lat_max) / deg_per_pixel)
    row_max = int((origin_lat - lat_min) / deg_per_pixel)

    # Pad
    left  = col_min - _PAD
    right = col_max + _PAD
    top   = row_min - _PAD
    bot   = row_max + _PAD

    # Enforce minimum size by expanding around the centroid
    cx = (left + right) // 2
    cy = (top + bot) // 2
    half_w = max((right - left) // 2, _MIN_SIZE // 2)
    half_h = max((bot - top) // 2, _MIN_SIZE // 2)
    left, right = cx - half_w, cx + half_w
    top, bot = cy - half_h, cy + half_h

    # Enforce maximum size
    if right - left > _MAX_SIZE:
        cx = (left + right) // 2
        left, right = cx - _MAX_SIZE // 2, cx + _MAX_SIZE // 2
    if bot - top > _MAX_SIZE:
        cy = (top + bot) // 2
        top, bot = cy - _MAX_SIZE // 2, cy + _MAX_SIZE // 2

    # Clamp to image bounds
    left  = max(0, left)
    top   = max(0, top)
    right = min(_IMG_SIZE, right)
    bot   = min(_IMG_SIZE, bot)

    return left, top, right, bot


def _wgs84_to_crop_pixels(
    footprint,
    transform: dict,
    crop_origin: tuple[int, int],   # (left, top) of the crop box
) -> list[tuple[int, int]]:
    """Convert polygon ring coordinates from WGS84 → image pixels → crop-relative pixels."""
    origin_lng = transform["origin_lng"]
    origin_lat = transform["origin_lat"]
    pixel_size_m = transform["pixel_size_m"]
    m_per_deg = transform.get("metres_per_degree", 111_000.0)
    deg_per_pixel = pixel_size_m / m_per_deg

    crop_left, crop_top = crop_origin
    result = []
    for lng, lat in footprint.coords[0]:  # exterior ring
        col = int((lng - origin_lng) / deg_per_pixel) - crop_left
        row = int((origin_lat - lat) / deg_per_pixel) - crop_top
        result.append((col, row))
    return result


def _fetch_image(client, bucket: str, cog_path: str):
    """Download a full scene from MinIO and return a PIL Image (RGBA mode)."""
    from PIL import Image

    resp = client.get_object(bucket, cog_path)
    data = resp.read()
    resp.close()
    img = Image.open(io.BytesIO(data))
    return img.convert("RGBA")


def _build_tile(flag, which: str) -> bytes:
    """Crop and (for T2) annotate a scene image; return PNG bytes.

    This is the hot path.  It is only called on cache miss and its result is
    stored in _tile_cache so repeat requests for the same (flag, which) are free.
    """
    from PIL import Image, ImageDraw
    from minio import Minio

    t0 = time.monotonic()

    detection = flag.detection
    job = detection.job
    scene = job.t1_scene if which == "t1" else job.t2_scene

    # Geo-transform: prefer scene metadata, fall back to T1 metadata
    meta = scene.metadata or {}
    transform = meta.get("geo_transform") or (job.t1_scene.metadata or {}).get("geo_transform")
    if not transform:
        raise ValueError(f"No geo_transform in scene #{scene.id} metadata")

    box = _crop_box(detection.footprint, transform)   # (left, top, right, bot)
    logger.debug("Flag #%d %s: crop_box=%s", flag.id, which, box)

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=getattr(settings, "MINIO_SECURE", False),
    )
    bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")

    img = _fetch_image(client, bucket, scene.cog_path)
    crop = img.crop(box)  # PIL box is (left, upper, right, lower)

    if which == "t2":
        # Draw detection polygon overlay on T2 only.
        # crop_origin is the (left, top) of the crop box — used to translate
        # image-space pixel coords into crop-relative coords.
        crop_origin = (box[0], box[1])
        poly_pixels = _wgs84_to_crop_pixels(detection.footprint, transform, crop_origin)

        overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.polygon(poly_pixels, fill=_FILL_COLOUR)
        # Draw outline with 2px width by drawing twice offset by 1px
        draw.polygon(poly_pixels, outline=_STROKE_COLOUR)
        # PIL's polygon outline is 1px; stroke a slightly expanded ring for 2px effect
        inflated = [(x + (1 if i % 2 == 0 else 0), y + (1 if i % 2 == 1 else 0))
                    for i, (x, y) in enumerate(poly_pixels)]
        draw.polygon(inflated, outline=_STROKE_COLOUR)

        crop = Image.alpha_composite(crop, overlay)

    # Encode to PNG bytes
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info("Flag #%d %s: rasterized in %.0f ms", flag.id, which, elapsed_ms)
    if elapsed_ms > 200:
        logger.warning("Flag #%d %s: rasterization took %.0f ms — consider a persistent cache", flag.id, which, elapsed_ms)

    return buf.getvalue()


class FlagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_class = FlagFilter
    search_fields = ["detection__parcel__upi", "detection__parcel__owner_name", "district"]
    ordering_fields = ["created_at", "severity", "status", "district", "detection__parcel__upi"]
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

    @action(detail=False, methods=["get"], url_path="export.csv", url_name="export_csv")
    def export_csv(self, request: Request) -> StreamingHttpResponse:
        """Stream all filtered flags as a CSV download."""
        qs = self.filter_queryset(self.get_queryset())

        today = date.today().isoformat()

        def _rows():
            yield [
                "flag_id", "flagged_at", "severity", "status",
                "parcel_upi", "owner_name", "district", "sector", "cell",
                "zone_type", "permit_status", "permit_no",
                "change_type", "confidence", "area_sqm",
                "latitude", "longitude",
            ]
            for flag in qs.iterator(chunk_size=200):
                det = flag.detection
                parcel = det.parcel
                centroid = det.footprint.centroid if det.footprint else None
                active_permit = parcel.permits.filter(status="active").first() if parcel else None
                has_active = active_permit is not None
                if has_active:
                    pstatus = "active"
                elif parcel and parcel.permits.filter(status="expired").exists():
                    pstatus = "expired"
                elif parcel and parcel.permits.exists():
                    pstatus = "other"
                else:
                    pstatus = "no_permit"
                yield [
                    flag.id,
                    flag.created_at.isoformat(),
                    flag.severity,
                    flag.status,
                    parcel.upi if parcel else "",
                    parcel.owner_name if parcel else "",
                    parcel.district if parcel else flag.district,
                    parcel.sector if parcel else "",
                    parcel.cell if parcel else "",
                    parcel.zone_type if parcel else "",
                    pstatus,
                    active_permit.permit_no if active_permit else "",
                    det.change_type or "",
                    round(det.confidence or 0, 4),
                    round(det.area_sqm or 0, 1),
                    round(centroid.y, 6) if centroid else "",
                    round(centroid.x, 6) if centroid else "",
                ]

        def _stream():
            buf = io.StringIO()
            writer = csv.writer(buf)
            for row in _rows():
                writer.writerow(row)
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()

        resp = StreamingHttpResponse(
            _stream(),
            content_type="text/csv",
        )
        resp["Content-Disposition"] = f'attachment; filename="imbonesha-flags-{today}.csv"'
        return resp

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
        """Stream a cropped, annotated T1 or T2 tile for a flag's detection footprint.

        T1: cropped to the detection bounding box (no overlay).
        T2: same crop window + red polygon drawn over the detected change.

        Using the same crop window for both ensures the swipe slider aligns.

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

        request._request.user = user
        flag = self.get_object()
        which = request.query_params.get("t", "t1")
        scene = flag.detection.job.t1_scene if which == "t1" else flag.detection.job.t2_scene

        if not scene or not scene.cog_path:
            return StreamingHttpResponse(status=404)

        cache_key = (flag.id, which)
        if cache_key not in _tile_cache:
            try:
                _tile_cache[cache_key] = _build_tile(flag, which)
            except Exception:
                logger.exception("Failed to build tile for flag #%d %s", flag.id, which)
                return StreamingHttpResponse(status=502)

        png_bytes = _tile_cache[cache_key]
        return StreamingHttpResponse(
            iter([png_bytes]),
            content_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )


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


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        CACHE_KEY = "analytics_summary"
        cached = cache.get(CACHE_KEY)
        if cached:
            return Response(cached)

        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        total = Flag.objects.count()
        awaiting = Flag.objects.filter(status__in=["pending", "assigned", "in_review"]).count()
        confirmed_30d = Flag.objects.filter(
            status="confirmed", updated_at__gte=thirty_days_ago
        ).count()

        # Flags over time — last 90 days, grouped by day + severity
        ninety_days_ago = now - timedelta(days=90)
        from django.db.models.functions import TruncDate
        daily_qs = (
            Flag.objects
            .filter(created_at__gte=ninety_days_ago)
            .annotate(day=TruncDate("created_at"))
            .values("day", "severity")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        # Pivot into {date: {severity: count}}
        day_map: dict[str, dict] = {}
        for row in daily_qs:
            d = row["day"].isoformat()
            day_map.setdefault(d, {"date": d, "low": 0, "medium": 0, "high": 0, "critical": 0})
            day_map[d][row["severity"]] = row["count"]
        flags_over_time = sorted(day_map.values(), key=lambda x: x["date"])

        # Flags by district
        district_qs = (
            Flag.objects
            .values("district")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        flags_by_district = [
            {"district": r["district"] or "Unknown", "count": r["count"]}
            for r in district_qs
        ]

        # Permit status breakdown from FlagListSerializer logic
        from .serializers import FlagListSerializer as _S
        permit_counts = {"active": 0, "expired": 0, "no_permit": 0, "other": 0}
        for flag in Flag.objects.select_related("detection__parcel").prefetch_related("detection__parcel__permits"):
            parcel = flag.detection.parcel if flag.detection else None
            if parcel is None:
                permit_counts["no_permit"] += 1
            elif parcel.permits.filter(status="active").exists():
                permit_counts["active"] += 1
            elif parcel.permits.filter(status="expired").exists():
                permit_counts["expired"] += 1
            elif parcel.permits.exists():
                permit_counts["other"] += 1
            else:
                permit_counts["no_permit"] += 1

        # Detection throughput — by week
        from django.db.models.functions import TruncWeek
        from detections.models import DetectionJob
        weekly_qs = (
            DetectionJob.objects
            .annotate(week=TruncWeek("created_at"))
            .values("week")
            .annotate(jobs=Count("id", distinct=True))
            .order_by("week")
        )
        # Detections per week
        from detections.models import Detection
        det_weekly = (
            Detection.objects
            .annotate(week=TruncWeek("created_at"))
            .values("week")
            .annotate(detections=Count("id"))
            .order_by("week")
        )
        det_map = {r["week"]: r["detections"] for r in det_weekly}
        throughput = [
            {
                "week": r["week"].strftime("%Y-W%V"),
                "jobs": r["jobs"],
                "detections": det_map.get(r["week"], 0),
            }
            for r in weekly_qs
            if r["week"]
        ]

        payload = {
            "kpis": {
                "total_flags": total,
                "awaiting_review": awaiting,
                "confirmed_unauthorized_30d": confirmed_30d,
                "avg_time_to_inspection_hours": None,
            },
            "flags_over_time": flags_over_time,
            "flags_by_district": flags_by_district,
            "permit_status_breakdown": permit_counts,
            "detection_throughput": throughput,
        }
        cache.set(CACHE_KEY, payload, 60)
        return Response(payload)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = ReportSerializer

    def get_queryset(self):
        return Report.objects.select_related("generated_by").order_by("-generated_at")

    def create(self, request: Request, *args, **kwargs) -> Response:
        flag_ids = request.data.get("flag_ids", [])
        title = request.data.get("title", f"Report — {date.today().isoformat()}")

        if not flag_ids:
            return Response({"detail": "flag_ids is required."}, status=status.HTTP_400_BAD_REQUEST)

        flags = list(Flag.objects.filter(id__in=flag_ids).select_related(
            "detection__parcel",
            "detection__job__t1_scene",
            "detection__job__t2_scene",
        ).prefetch_related("detection__parcel__permits"))

        if not flags:
            return Response({"detail": "No matching flags found."}, status=status.HTTP_400_BAD_REQUEST)

        import uuid as _uuid
        report_id = _uuid.uuid4()

        from .services.reports import generate_flag_report
        pdf_bytes = generate_flag_report([f.id for f in flags], request.user)

        # Store in MinIO
        file_path = ""
        try:
            from minio import Minio
            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=getattr(settings, "MINIO_SECURE", False),
            )
            bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
            object_name = f"reports/{report_id}.pdf"
            client.put_object(
                bucket, object_name,
                io.BytesIO(pdf_bytes), len(pdf_bytes),
                content_type="application/pdf",
            )
            file_path = object_name
        except Exception:
            logger.exception("Failed to store report PDF in MinIO")

        report = Report.objects.create(
            id=report_id,
            title=title,
            generated_by=request.user,
            flag_ids=[f.id for f in flags],
            flag_count=len(flags),
            file_path=file_path,
            file_size=len(pdf_bytes),
        )

        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request: Request, pk=None) -> StreamingHttpResponse:
        report = self.get_object()
        if not report.file_path:
            # Re-generate on the fly
            flags = list(Flag.objects.filter(id__in=report.flag_ids))
            from .services.reports import generate_flag_report
            pdf_bytes = generate_flag_report([f.id for f in flags], request.user)
        else:
            try:
                from minio import Minio
                client = Minio(
                    settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=getattr(settings, "MINIO_SECURE", False),
                )
                bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
                resp = client.get_object(bucket, report.file_path)
                pdf_bytes = resp.read()
                resp.close()
            except Exception:
                logger.exception("Failed to fetch report from MinIO, regenerating")
                flags = list(Flag.objects.filter(id__in=report.flag_ids))
                from .services.reports import generate_flag_report
                pdf_bytes = generate_flag_report([f.id for f in flags], request.user)

        filename = f"imbonesha-report-{report.id}.pdf"
        response = StreamingHttpResponse(
            iter([pdf_bytes]),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
