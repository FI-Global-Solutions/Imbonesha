"""Django admin for the detections app."""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html

from .models import Detection, DetectionJob, JobStatus


_JOB_STATUS_COLOURS = {
    JobStatus.QUEUED:    ("#8a8a8a", "#fff"),
    JobStatus.RUNNING:   ("#1a6db5", "#fff"),
    JobStatus.COMPLETED: ("#1f9640", "#fff"),
    JobStatus.FAILED:    ("#d01a1a", "#fff"),
}


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:3px;font-size:11px;font-weight:bold;'
        f'letter-spacing:0.5px;white-space:nowrap">{text.upper()}</span>'
    )


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
        "status_badge",
        "model_version",
        "detection_count",
        "inference_time",
        "started_at",
    )
    list_filter = ("status", "model_version")
    search_fields = ("t1_scene__aoi__name", "t2_scene__aoi__name", "model_version")
    readonly_fields = ("created_at", "started_at", "ran_at", "error_message")
    inlines = [DetectionInline]

    @admin.display(description="Status")
    def status_badge(self, obj: DetectionJob):
        bg, fg = _JOB_STATUS_COLOURS.get(obj.status, ("#888", "#fff"))
        return format_html(_badge(obj.get_status_display(), bg, fg))

    @admin.display(description="Detections")
    def detection_count(self, obj: DetectionJob) -> int:
        return obj.detections.count()

    @admin.display(description="Inference time")
    def inference_time(self, obj: DetectionJob) -> str:
        if obj.started_at and obj.ran_at:
            delta = obj.ran_at - obj.started_at
            secs = int(delta.total_seconds())
            return f"{secs}s"
        return "—"


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
