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

from accounts.models import User, UserRole
from notifications.services import NotificationService
from .filters import FlagFilter
from .models import AuditLog, Flag, Inspection, InspectionPhoto, InspectionVerdict, Report, haversine_meters
from .serializers import FlagDetailSerializer, FlagListSerializer, InspectionPhotoSerializer, ReportSerializer

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
_FILL_COLOUR = (220, 38, 38, 90)       # red-600 @ ~35% alpha  — primary detection
_STROKE_COLOUR = (220, 38, 38, 255)    # solid red-600         — primary detection
_CTX_FILL_COLOUR = (251, 146, 60, 40)  # orange-400 @ ~15% alpha — neighbouring detections
_CTX_STROKE_COLOUR = (251, 146, 60, 180) # orange-400 @ ~70%  — neighbouring detections


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

    col_min = round((lng_min - origin_lng) / deg_per_pixel)
    col_max = round((lng_max - origin_lng) / deg_per_pixel)
    row_min = round((origin_lat - lat_max) / deg_per_pixel)
    row_max = round((origin_lat - lat_min) / deg_per_pixel)

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
        col = round((lng - origin_lng) / deg_per_pixel) - crop_left
        row = round((origin_lat - lat) / deg_per_pixel) - crop_top
        result.append((col, row))
    return result


def _fetch_image(client, bucket: str, cog_path: str):
    """Download a full scene and return a PIL Image (RGBA mode).

    If cog_path is a full URL (Supabase Storage), fetch directly via httpx.
    Otherwise use the MinIO client (local dev).
    """
    import httpx
    from PIL import Image

    if cog_path.startswith("http://") or cog_path.startswith("https://"):
        response = httpx.get(cog_path, timeout=30)
        response.raise_for_status()
        data = response.content
    else:
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

    # Use the displayed scene's own geo-transform for the crop box and polygon
    # overlay.  T1 and T2 may have different tile origins, so using T1's
    # transform for a T2 overlay would produce a systematic pixel offset.
    # Fall back to T1 only when T2 metadata is genuinely absent (e.g. older
    # jobs ingested before T2 transforms were stored).
    meta = scene.metadata or {}
    transform = meta.get("geo_transform")
    if transform is None and which == "t2":
        transform = (job.t1_scene.metadata or {}).get("geo_transform")
        if transform:
            logger.warning(
                "Flag #%d: T2 scene #%d has no geo_transform — falling back to T1. "
                "Re-run the detection job to store T2 metadata.",
                flag.id, scene.id,
            )
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
        # Draw all detections from the same job that fall within the crop window,
        # so inspectors can see the full scene context — not just the one polygon.
        # Neighbouring detections are drawn in dim orange first; the primary
        # detection is drawn last in solid red so it is always clearly on top.
        crop_origin = (box[0], box[1])
        crop_left, crop_top, crop_right, crop_bot = box
        crop_w = crop_right - crop_left
        crop_h = crop_bot - crop_top

        # Collect all sibling detections whose footprint overlaps the crop window.
        from django.contrib.gis.geos import Polygon as GEOSPolygon
        deg_per_px = transform["pixel_size_m"] / transform.get("metres_per_degree", 111_000.0)
        origin_lng = transform["origin_lng"]
        origin_lat = transform["origin_lat"]
        crop_lng_min = origin_lng + crop_left * deg_per_px
        crop_lat_max = origin_lat - crop_top * deg_per_px
        crop_lng_max = origin_lng + crop_right * deg_per_px
        crop_lat_min = origin_lat - crop_bot * deg_per_px
        crop_bbox = GEOSPolygon.from_bbox((crop_lng_min, crop_lat_min, crop_lng_max, crop_lat_max))

        from .models import Flag as FlagModel
        siblings = (
            FlagModel.objects
            .filter(detection__job=job)
            .exclude(detection=detection)
            .filter(detection__footprint__intersects=crop_bbox)
            .select_related("detection")
        )

        overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        def _draw_poly(pts, fill, stroke):
            draw.polygon(pts, fill=fill)
            draw.polygon(pts, outline=stroke)
            inflated = [(x + (1 if i % 2 == 0 else 0), y + (1 if i % 2 == 1 else 0))
                        for i, (x, y) in enumerate(pts)]
            draw.polygon(inflated, outline=stroke)

        # Draw neighbouring detections in dim orange (context layer).
        for sibling in siblings:
            pts = _wgs84_to_crop_pixels(sibling.detection.footprint, transform, crop_origin)
            # Skip polygons that land entirely outside the crop (clamp rounding edge cases).
            if all(x < 0 or x > crop_w or y < 0 or y > crop_h for x, y in pts):
                continue
            _draw_poly(pts, _CTX_FILL_COLOUR, _CTX_STROKE_COLOUR)

        # Draw the primary detection in solid red on top.
        primary_pts = _wgs84_to_crop_pixels(detection.footprint, transform, crop_origin)
        _draw_poly(primary_pts, _FILL_COLOUR, _STROKE_COLOUR)

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
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_class = FlagFilter
    search_fields = ["detection__parcel__upi", "detection__parcel__owner_name", "district"]
    ordering_fields = ["created_at", "severity", "status", "district", "detection__parcel__upi"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = (
            Flag.objects
            .select_related(
                "detection__job__t1_scene",
                "detection__job__t2_scene",
                "detection__parcel",
                "assigned_to",
                "assigned_by",
            )
            .prefetch_related(
                "detection__parcel__permits",
                "inspections__inspector",
                "audit_logs__actor",
            )
            .order_by("-created_at")
        )
        user = self.request.user
        if user.role == UserRole.INSPECTOR:
            qs = qs.filter(assigned_to=user)
        elif user.role == UserRole.DISTRICT_ADMIN and user.district:
            qs = qs.filter(district=user.district)
        return qs

    def get_serializer_class(self):
        if self.action in ("retrieve", "imagery", "assign", "unassign", "inspect"):
            return FlagDetailSerializer
        return FlagListSerializer

    def _require_admin(self, request) -> Response | None:
        """Return 403 Response if user cannot assign flags, else None."""
        if request.user.role not in (UserRole.ADMIN, UserRole.DISTRICT_ADMIN):
            return Response(
                {"detail": "You do not have permission to assign flags."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _require_rha_or_admin(self, request) -> Response | None:
        if request.user.role not in (UserRole.ADMIN, UserRole.DISTRICT_ADMIN, UserRole.RHA_OFFICER):
            return Response(
                {"detail": "You do not have permission to delete flags."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def destroy(self, request: Request, pk=None) -> Response:
        denied = self._require_rha_or_admin(request)
        if denied:
            return denied
        flag = self.get_object()
        detection = flag.detection
        flag.delete()
        # OneToOneField — detection has no other flags after this delete, safe to remove.
        detection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["delete"], url_path="bulk-delete")
    def bulk_delete(self, request: Request) -> Response:
        denied = self._require_rha_or_admin(request)
        if denied:
            return denied
        ids = request.data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return Response({"detail": "Provide a non-empty list of flag ids."}, status=status.HTTP_400_BAD_REQUEST)
        flags = Flag.objects.filter(id__in=ids)
        detection_ids = list(flags.values_list("detection_id", flat=True))
        deleted_count = flags.count()
        flags.delete()
        # Delete associated detections (OneToOne — no other flags can reference them).
        from detections.models import Detection
        Detection.objects.filter(id__in=detection_ids).delete()
        return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request: Request, pk=None) -> Response:
        denied = self._require_admin(request)
        if denied:
            return denied

        flag = self.get_object()
        inspector_id = request.data.get("inspector_id")
        if not inspector_id:
            return Response({"detail": "inspector_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            inspector = User.objects.get(pk=inspector_id, role=UserRole.INSPECTOR)
        except User.DoesNotExist:
            return Response({"detail": "Inspector not found."}, status=status.HTTP_404_NOT_FOUND)

        if not flag.can_transition_to("assigned"):
            return Response(
                {"detail": f"Cannot assign a flag with status '{flag.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = flag.status
        flag.assigned_to = inspector
        flag.assigned_by = request.user
        flag.assigned_at = timezone.now()
        flag.status = "assigned"
        flag._actor = request.user
        flag._pre_save_snapshot = {"status": old_status, "severity": flag.severity, "assigned_to_id": None}
        flag.save(update_fields=["status", "assigned_to", "assigned_by", "assigned_at", "updated_at"])

        AuditLog.objects.create(
            flag=flag,
            actor=request.user,
            event="assigned",
            before={"status": old_status, "assigned_to": None},
            after={"status": "assigned", "assigned_to": inspector.email},
            message=f"Assigned to {inspector.get_full_name() or inspector.email} by {request.user.email}",
        )
        NotificationService.notify_flag_assigned(flag, inspector, request.user)
        return Response(FlagDetailSerializer(flag, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="unassign")
    def unassign(self, request: Request, pk=None) -> Response:
        denied = self._require_admin(request)
        if denied:
            return denied

        flag = self.get_object()
        if flag.status != "assigned":
            return Response(
                {"detail": "Only assigned flags can be unassigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prev_inspector = flag.assigned_to
        flag.assigned_to = None
        flag.assigned_by = None
        flag.assigned_at = None
        flag.status = "pending"
        flag._actor = request.user
        flag._pre_save_snapshot = {"status": "assigned", "severity": flag.severity, "assigned_to_id": prev_inspector.pk if prev_inspector else None}
        flag.save(update_fields=["status", "assigned_to", "assigned_by", "assigned_at", "updated_at"])

        AuditLog.objects.create(
            flag=flag,
            actor=request.user,
            event="unassigned",
            before={"status": "assigned", "assigned_to": prev_inspector.email if prev_inspector else None},
            after={"status": "pending", "assigned_to": None},
            message=f"Unassigned by {request.user.email}",
        )
        return Response(FlagDetailSerializer(flag, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request: Request) -> Response:
        denied = self._require_admin(request)
        if denied:
            return denied

        flag_ids = request.data.get("flag_ids", [])
        inspector_id = request.data.get("inspector_id")

        if not flag_ids:
            return Response({"detail": "flag_ids is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not inspector_id:
            return Response({"detail": "inspector_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            inspector = User.objects.get(pk=inspector_id, role=UserRole.INSPECTOR)
        except User.DoesNotExist:
            return Response({"detail": "Inspector not found."}, status=status.HTTP_404_NOT_FOUND)

        flags = Flag.objects.filter(id__in=flag_ids)
        now = timezone.now()
        assigned = skipped = 0
        errors = []

        for flag in flags:
            if not flag.can_transition_to("assigned"):
                skipped += 1
                errors.append({"flag_id": flag.id, "reason": f"Cannot assign from status '{flag.status}'"})
                continue
            old_status = flag.status
            flag.assigned_to = inspector
            flag.assigned_by = request.user
            flag.assigned_at = now
            flag.status = "assigned"
            flag._actor = request.user
            flag._pre_save_snapshot = {"status": old_status, "severity": flag.severity, "assigned_to_id": None}
            flag.save(update_fields=["status", "assigned_to", "assigned_by", "assigned_at", "updated_at"])
            AuditLog.objects.create(
                flag=flag,
                actor=request.user,
                event="assigned",
                before={"status": old_status, "assigned_to": None},
                after={"status": "assigned", "assigned_to": inspector.email},
                message=f"Bulk assigned to {inspector.get_full_name() or inspector.email} by {request.user.email}",
            )
            NotificationService.notify_flag_assigned(flag, inspector, request.user)
            assigned += 1

        return Response({"assigned": assigned, "skipped": skipped, "errors": errors})

    @action(detail=True, methods=["post"], url_path="inspect")
    def inspect(self, request: Request, pk=None) -> Response:
        flag = self.get_object()
        user = request.user

        # Only the assigned inspector can submit an inspection.
        if user.role == UserRole.INSPECTOR and flag.assigned_to != user:
            return Response(
                {"detail": "You can only inspect flags assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.role not in (UserRole.ADMIN, UserRole.DISTRICT_ADMIN, UserRole.INSPECTOR):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        verdict = request.data.get("verdict")
        if verdict not in InspectionVerdict.values:
            return Response(
                {"detail": f"verdict must be one of: {', '.join(InspectionVerdict.values)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        visited_at = request.data.get("visited_at")
        if not visited_at:
            return Response({"detail": "visited_at is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Require at least one photo — GPS distance does not block submission.
        photo_ids = request.data.get("photo_ids") or []
        if not photo_ids:
            return Response(
                {"error": "At least one site photo is required to submit an inspection."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        photos = InspectionPhoto.objects.filter(id__in=photo_ids, flag=flag)
        if not photos.exists():
            return Response(
                {"error": "Provided photos not found for this flag."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inspection = Inspection.objects.create(
            flag=flag,
            inspector=user,
            verdict=verdict,
            notes=request.data.get("notes", ""),
            construction_stage=request.data.get("construction_stage", ""),
            estimated_floors=request.data.get("estimated_floors"),
            occupancy_observed=bool(request.data.get("occupancy_observed", False)),
            visited_at=visited_at,
            inspector_lat=request.data.get("inspector_lat"),
            inspector_lng=request.data.get("inspector_lng"),
            inspector_accuracy_m=request.data.get("inspector_accuracy_m"),
            inspector_location_name=request.data.get("inspector_location_name", ""),
            distance_to_site_m=request.data.get("distance_to_site_m"),
        )
        # Link uploaded photos to this inspection record.
        photos.update(inspection=inspection)

        # Map verdict directly to flag status (immediate transition, no in_review gate).
        verdict_to_status = {
            "confirmed": "confirmed",
            "dismissed": "dismissed",
            "monitoring": "monitoring",
            "inaccessible": "inaccessible",
            "data_error": "data_error",
        }
        new_status = verdict_to_status[verdict]
        old_status = flag.status

        flag._actor = user
        flag._pre_save_snapshot = {"status": old_status, "severity": flag.severity, "assigned_to_id": flag.assigned_to_id}
        flag.status = new_status
        flag.save(update_fields=["status", "updated_at"])

        AuditLog.objects.create(
            flag=flag,
            actor=user,
            event="inspection_submitted",
            before={"status": old_status},
            after={"status": new_status, "verdict": verdict},
            message=f"Inspection submitted by {user.get_full_name() or user.email}: {InspectionVerdict(verdict).label}",
        )
        NotificationService.notify_inspection_complete(flag, inspection)

        flag.refresh_from_db()
        return Response(FlagDetailSerializer(flag, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="photos")
    def photos(self, request: Request, pk=None) -> Response:
        flag = self.get_object()
        user = request.user

        if request.method == "GET":
            qs = InspectionPhoto.objects.filter(flag=flag)
            return Response(InspectionPhotoSerializer(qs, many=True).data)

        # POST — upload a new photo
        if user.role == UserRole.INSPECTOR and flag.assigned_to != user:
            return Response({"detail": "You can only upload photos for flags assigned to you."}, status=status.HTTP_403_FORBIDDEN)

        photo_file = request.FILES.get("photo")
        if not photo_file:
            return Response({"detail": "photo file is required."}, status=status.HTTP_400_BAD_REQUEST)
        for field in ("latitude", "longitude", "captured_at"):
            if not request.data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lat = float(request.data["latitude"])
            lng = float(request.data["longitude"])
        except (ValueError, TypeError):
            return Response({"detail": "latitude and longitude must be numeric."}, status=status.HTTP_400_BAD_REQUEST)

        accuracy = request.data.get("accuracy_meters")
        try:
            accuracy = float(accuracy) if accuracy else None
        except (ValueError, TypeError):
            accuracy = None

        # Resize to max 1920px on longest side using Pillow.
        try:
            from PIL import Image as PILImage
            import io as _io
            img = PILImage.open(photo_file)
            img = img.convert("RGB")
            max_dim = 1920
            if max(img.width, img.height) > max_dim:
                ratio = max_dim / max(img.width, img.height)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), PILImage.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            img_bytes = buf.read()
        except Exception as exc:
            logger.error("Image resize failed: %s", exc)
            return Response({"detail": "Invalid image file."}, status=status.HTTP_400_BAD_REQUEST)

        # Compute distance from detection centroid using Haversine.
        distance = None
        try:
            centroid = flag.detection.footprint.centroid
            if centroid:
                distance = haversine_meters(lat, lng, centroid.y, centroid.x)
        except Exception:
            pass

        # Store in MinIO under inspection-photos/{flag_id}/{photo_id}.jpg
        import uuid as _uuid
        photo_id = _uuid.uuid4()
        object_key = f"inspection-photos/{flag.id}/{photo_id}.jpg"
        try:
            from minio import Minio
            minio_client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=getattr(settings, "MINIO_SECURE", False),
            )
            bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
            minio_client.put_object(
                bucket, object_key,
                _io.BytesIO(img_bytes), len(img_bytes),
                content_type="image/jpeg",
            )
        except Exception as exc:
            logger.exception("MinIO upload failed for photo %s: %s", photo_id, exc)
            return Response({"detail": "Photo storage failed. Try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        photo = InspectionPhoto.objects.create(
            id=photo_id,
            flag=flag,
            uploaded_by=user,
            object_key=object_key,
            caption=request.data.get("caption", ""),
            latitude=lat,
            longitude=lng,
            accuracy_meters=accuracy,
            captured_at=request.data["captured_at"],
            distance_from_site_m=distance,
        )

        return Response(InspectionPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path=r"photos/(?P<photo_id>[0-9a-f-]+)/proxy",
            permission_classes=[AllowAny])
    def photo_proxy(self, request: Request, pk=None, photo_id=None) -> StreamingHttpResponse:
        """Proxy an inspection photo from MinIO so the browser never needs a direct MinIO URL.

        Accepts JWT via Authorization header OR ?token= query param (same pattern as /stream/).
        """
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import TokenError

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

        try:
            photo = InspectionPhoto.objects.get(id=photo_id, flag__id=pk)
        except InspectionPhoto.DoesNotExist:
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
            response = client.get_object(bucket, photo.object_key)
            data = response.read()
            response.close()
            response.release_conn()
        except Exception:
            return StreamingHttpResponse(status=502)

        return StreamingHttpResponse(
            streaming_content=iter([data]),
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=900"},
        )

    @action(detail=False, methods=["get"], url_path="export.csv", url_name="export_csv",
            permission_classes=[AllowAny])
    def export_csv(self, request: Request) -> StreamingHttpResponse:
        """Stream all filtered flags as a CSV download.

        Accepts JWT via Authorization header OR ?token= query param so that
        a plain <a href> navigation (which cannot set headers) works.
        """
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import TokenError

        user = request.user if request.user and request.user.is_authenticated else None
        if not user:
            raw = request.query_params.get("token")
            if raw:
                try:
                    jwt_auth = JWTAuthentication()
                    validated = jwt_auth.get_validated_token(raw)
                    user = jwt_auth.get_user(validated)
                except (TokenError, Exception):
                    pass
        if not user or not user.is_authenticated:
            from rest_framework.response import Response as DRFResponse
            return DRFResponse({"detail": "Authentication credentials were not provided."}, status=401)

        request._request.user = user
        request._user = user  # patch DRF cached user so get_queryset sees it
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
        request._user = user  # also patch DRF's cached user so get_queryset sees it
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

    Sign using the internal minio:9000 endpoint (reachable from the api
    container), then rewrite the origin to MINIO_PUBLIC_ENDPOINT so the URL
    is browser-resolvable. MinIO's MINIO_SERVER_URL=http://localhost:9007
    makes it accept requests where the signed host is minio:9000 but the
    actual request arrives at localhost:9007.
    """
    if not cog_path:
        return None
    try:
        from minio import Minio
        from urllib.parse import urlparse, urlunparse

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=getattr(settings, "MINIO_SECURE", False),
        )
        bucket = getattr(settings, "MINIO_BUCKET", "imbonesha-imagery")
        url = client.presigned_get_object(bucket, cog_path, expires=timedelta(minutes=15))

        public_endpoint = getattr(settings, "MINIO_PUBLIC_ENDPOINT", None)
        if public_endpoint:
            parsed = urlparse(url)
            public = urlparse(public_endpoint)
            url = urlunparse(parsed._replace(scheme=public.scheme, netloc=public.netloc))

        return url
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        CACHE_KEY = "analytics_summary"
        try:
            cached = cache.get(CACHE_KEY)
            if cached:
                return Response(cached)
        except Exception:
            cached = None

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

        # Flags by district — collapse null/empty into "Unknown" and merge duplicates
        district_qs = (
            Flag.objects
            .values("district")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        district_totals: dict[str, int] = {}
        for r in district_qs:
            name = r["district"] or "Unknown"
            district_totals[name] = district_totals.get(name, 0) + r["count"]
        flags_by_district = [
            {"district": name, "count": count}
            for name, count in sorted(district_totals.items(), key=lambda x: -x[1])
            if count > 0
        ]

        # Permit status breakdown from stored permit_status field
        permit_qs = (
            Flag.objects
            .values("permit_status")
            .annotate(count=Count("id"))
        )
        permit_counts = {row["permit_status"]: row["count"] for row in permit_qs}

        # Flag status breakdown
        status_qs = (
            Flag.objects
            .values("status")
            .annotate(count=Count("id"))
        )
        status_counts = {r["status"]: r["count"] for r in status_qs}

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
            "status_breakdown": status_counts,
            "detection_throughput": throughput,
        }
        try:
            cache.set(CACHE_KEY, payload, 60)
        except Exception:
            pass
        return Response(payload)


# ---------------------------------------------------------------------------
# Inspectors workload
# ---------------------------------------------------------------------------

class InspectorWorkloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if request.user.role not in (UserRole.ADMIN, UserRole.DISTRICT_ADMIN):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        qs = User.objects.filter(role=UserRole.INSPECTOR)
        if request.user.role == UserRole.DISTRICT_ADMIN and request.user.district:
            qs = qs.filter(district=request.user.district)

        result = []
        for inspector in qs.order_by("first_name", "last_name"):
            assigned_count = Flag.objects.filter(assigned_to=inspector, status="assigned").count()
            completed_count = Inspection.objects.filter(inspector=inspector).count()
            result.append({
                "inspector_id": inspector.pk,
                "name": inspector.get_full_name() or inspector.email,
                "email": inspector.email,
                "district": inspector.district,
                "assigned_count": assigned_count,
                "completed_count": completed_count,
            })
        return Response(result)


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
