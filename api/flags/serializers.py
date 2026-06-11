"""Serializers for flags app.

The FlagDetailSerializer returns everything the dashboard drawer needs
in a single response — parcel, active permit, detection geometry, and
image scene IDs. No secondary round-trips required.
"""

from rest_framework import serializers

from accounts.models import User
from detections.models import Detection
from imagery.models import ImageScene
from parcels.models import Parcel, Permit

from .models import AuditLog, Flag, Inspection, InspectionPhoto, PermitStatus, Report, VALID_TRANSITIONS


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
    permit_status_display = serializers.CharField(source="get_permit_status_display", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    assigned_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Flag
        fields = (
            "id", "severity", "status", "district",
            "parcel_upi", "owner_name",
            "permit_status", "permit_status_display", "severity_reason",
            "centroid_lat", "centroid_lng",
            "assigned_to_name", "assigned_at", "assigned_by_email",
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

    def get_assigned_to_name(self, obj: Flag) -> str | None:
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.email
        return None

    def get_assigned_by_email(self, obj: Flag) -> str | None:
        return obj.assigned_by.email if obj.assigned_by else None


class _InspectorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "district")

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.email


class _InspectionSerializer(serializers.ModelSerializer):
    inspector_name = serializers.SerializerMethodField()

    class Meta:
        model = Inspection
        fields = (
            "id", "verdict", "notes", "construction_stage",
            "estimated_floors", "occupancy_observed",
            "visited_at", "submitted_at", "inspector_name",
            "inspector_lat", "inspector_lng", "inspector_accuracy_m",
            "inspector_location_name", "distance_to_site_m",
        )

    def get_inspector_name(self, obj: Inspection) -> str:
        return obj.inspector.get_full_name() or obj.inspector.email


class _AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ("id", "event", "before", "after", "message", "actor_name", "timestamp")

    def get_actor_name(self, obj: AuditLog) -> str | None:
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.email
        return None


class FlagDetailSerializer(FlagListSerializer):
    parcel = serializers.SerializerMethodField()
    detection = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    inspections = serializers.SerializerMethodField()
    audit_logs = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    permit_details = serializers.SerializerMethodField()

    class Meta(FlagListSerializer.Meta):
        fields = FlagListSerializer.Meta.fields + (
            "parcel", "detection", "notes",
            "assigned_to", "assigned_at", "assigned_by_email",
            "inspections", "audit_logs", "available_transitions", "photos",
            "permit_details",
        )

    def get_parcel(self, obj: Flag) -> dict | None:
        try:
            return _ParcelSerializer(obj.detection.parcel).data
        except Exception:
            return None

    def get_permit_details(self, obj: Flag) -> list:
        try:
            parcel = obj.detection.parcel
            if parcel is None:
                return []
            return [
                {
                    "permit_no": p.permit_no,
                    "category": p.category,
                    "category_display": p.get_category_display(),
                    "status": p.status,
                    "issued_date": p.issued_date,
                    "expiry_date": p.expiry_date,
                    "intended_use": p.intended_use,
                    "max_floors_allowed": p.max_floors_allowed,
                    "max_footprint_sqm": p.max_footprint_sqm,
                    "applicant_name": p.applicant_name,
                }
                for p in parcel.permits.all()
            ]
        except Exception:
            return []

    def get_detection(self, obj: Flag) -> dict:
        return _DetectionSerializer(obj.detection).data

    def get_assigned_to(self, obj: Flag) -> dict | None:
        if obj.assigned_to:
            return _InspectorSerializer(obj.assigned_to).data
        return None

    def get_inspections(self, obj: Flag) -> list:
        return _InspectionSerializer(obj.inspections.all(), many=True).data

    def get_audit_logs(self, obj: Flag) -> list:
        return _AuditLogSerializer(obj.audit_logs.all()[:20], many=True).data

    def get_available_transitions(self, obj: Flag) -> list[str]:
        return sorted(VALID_TRANSITIONS.get(obj.status, set()))

    def get_photos(self, obj: Flag) -> list:
        return InspectionPhotoSerializer(obj.photos.all(), many=True).data


class InspectionPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = InspectionPhoto
        fields = (
            "id", "inspection_id", "url", "caption",
            "latitude", "longitude", "accuracy_meters",
            "captured_at", "distance_from_site_m", "uploaded_at",
        )

    def get_url(self, obj: InspectionPhoto) -> str | None:
        return f"/api/v1/flags/{obj.flag_id}/photos/{obj.id}/proxy/"


class ReportSerializer(serializers.ModelSerializer):
    generated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "id", "title", "generated_by", "generated_by_name",
            "generated_at", "flag_ids", "flag_count",
            "file_size",
        )
        read_only_fields = ("id", "generated_at", "flag_count", "file_size", "generated_by")

    def get_generated_by_name(self, obj: Report) -> str | None:
        if obj.generated_by:
            return obj.generated_by.get_full_name() or obj.generated_by.email
        return None
