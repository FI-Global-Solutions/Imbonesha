"""Serializers for flags app.

The FlagDetailSerializer returns everything the dashboard drawer needs
in a single response — parcel, active permit, detection geometry, and
image scene IDs. No secondary round-trips required.
"""

from rest_framework import serializers

from detections.models import Detection
from imagery.models import ImageScene
from parcels.models import Parcel, Permit

from .models import Flag


class _PermitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permit
        fields = (
            "permit_no", "category", "get_category_display",
            "status", "issued_date", "expiry_date",
            "intended_use", "max_floors_allowed", "max_footprint_sqm", "applicant_name",
        )

    get_category_display = serializers.CharField(source="get_category_display", read_only=True)


class _ParcelSerializer(serializers.ModelSerializer):
    active_permit = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = (
            "upi", "owner_name", "land_use", "district", "sector", "cell",
            "zone_type", "active_permit",
        )

    def get_active_permit(self, obj: Parcel) -> dict | None:
        permit = obj.permits.filter(status="active").order_by("-issued_date").first()
        if permit is None:
            return None
        return _PermitSerializer(permit).data


class _SceneRef(serializers.ModelSerializer):
    class Meta:
        model = ImageScene
        fields = ("id", "captured_at", "source", "cog_path")


class _DetectionSerializer(serializers.ModelSerializer):
    centroid_lat = serializers.SerializerMethodField()
    centroid_lng = serializers.SerializerMethodField()
    t1_scene = serializers.SerializerMethodField()
    t2_scene = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = (
            "id", "change_type", "confidence", "area_sqm",
            "centroid_lat", "centroid_lng", "t1_scene", "t2_scene",
        )

    def get_centroid_lat(self, obj: Detection) -> float | None:
        c = obj.footprint.centroid
        return round(c.y, 6) if c else None

    def get_centroid_lng(self, obj: Detection) -> float | None:
        c = obj.footprint.centroid
        return round(c.x, 6) if c else None

    def get_t1_scene(self, obj: Detection) -> dict | None:
        scene = obj.job.t1_scene
        return _SceneRef(scene).data if scene else None

    def get_t2_scene(self, obj: Detection) -> dict | None:
        scene = obj.job.t2_scene
        return _SceneRef(scene).data if scene else None


class FlagListSerializer(serializers.ModelSerializer):
    parcel_upi = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    centroid_lat = serializers.SerializerMethodField()
    centroid_lng = serializers.SerializerMethodField()
    permit_status = serializers.SerializerMethodField()

    class Meta:
        model = Flag
        fields = (
            "id", "severity", "status", "district",
            "parcel_upi", "owner_name", "permit_status",
            "centroid_lat", "centroid_lng",
            "created_at", "updated_at",
        )

    def get_parcel_upi(self, obj: Flag) -> str | None:
        return obj.detection.parcel_id

    def get_owner_name(self, obj: Flag) -> str | None:
        try:
            return obj.detection.parcel.owner_name
        except Exception:
            return None

    def get_centroid_lat(self, obj: Flag) -> float | None:
        c = obj.detection.footprint.centroid
        return round(c.y, 6) if c else None

    def get_centroid_lng(self, obj: Flag) -> float | None:
        c = obj.detection.footprint.centroid
        return round(c.x, 6) if c else None

    def get_permit_status(self, obj: Flag) -> str | None:
        try:
            parcel = obj.detection.parcel
            if parcel is None:
                return "no_parcel"
            active = parcel.permits.filter(status="active").exists()
            if active:
                return "active"
            expired = parcel.permits.filter(status="expired").exists()
            if expired:
                return "expired"
            if parcel.permits.exists():
                return "other"
            return "no_permit"
        except Exception:
            return None


class FlagDetailSerializer(FlagListSerializer):
    parcel = serializers.SerializerMethodField()
    detection = serializers.SerializerMethodField()

    class Meta(FlagListSerializer.Meta):
        fields = FlagListSerializer.Meta.fields + ("parcel", "detection", "notes")

    def get_parcel(self, obj: Flag) -> dict | None:
        try:
            return _ParcelSerializer(obj.detection.parcel).data
        except Exception:
            return None

    def get_detection(self, obj: Flag) -> dict:
        return _DetectionSerializer(obj.detection).data
