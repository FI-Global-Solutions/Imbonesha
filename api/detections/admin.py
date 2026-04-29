"""Django admin for the detections app."""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Detection, DetectionJob


class DetectionInline(admin.TabularInline):
    model = Detection
    extra = 0
    fields = ("change_type", "confidence", "area_sqm", "parcel", "footprint_hash", "created_at")
    readonly_fields = ("footprint_hash", "created_at")
    show_change_link = True


@admin.register(DetectionJob)
class DetectionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "t1_scene",
        "t2_scene",
        "status",
        "model_version",
        "detection_count",
        "started_at",
        "ran_at",
    )
    list_filter = ("status", "model_version")
    search_fields = ("t1_scene__aoi__name", "t2_scene__aoi__name", "model_version")
    readonly_fields = ("created_at", "started_at", "ran_at", "error_message")
    inlines = [DetectionInline]

    @admin.display(description="Detections")
    def detection_count(self, obj: DetectionJob) -> int:
        return obj.detections.count()


@admin.register(Detection)
class DetectionAdmin(GISModelAdmin):
    list_display = (
        "id",
        "job",
        "change_type",
        "confidence",
        "area_sqm",
        "parcel",
        "created_at",
    )
    list_filter = ("change_type", "job__status")
    search_fields = ("parcel__upi", "footprint_hash")
    readonly_fields = ("footprint_hash", "created_at")
    autocomplete_fields = ("parcel",)
