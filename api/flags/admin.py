"""Django admin for the flags app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog, Flag, FlagStatus, Inspection, Severity


_SEVERITY_COLOURS = {
    Severity.LOW:      ("#1f9640", "#fff"),
    Severity.MEDIUM:   ("#d4a000", "#000"),
    Severity.HIGH:     ("#e06010", "#fff"),
    Severity.CRITICAL: ("#d01a1a", "#fff"),
}

_STATUS_COLOURS = {
    FlagStatus.PENDING:   ("#8a8a8a", "#fff"),
    FlagStatus.ASSIGNED:  ("#1a6db5", "#fff"),
    FlagStatus.IN_REVIEW: ("#7b4fbf", "#fff"),
    FlagStatus.CONFIRMED: ("#c03030", "#fff"),
    FlagStatus.DISMISSED: ("#4a7c59", "#fff"),
    FlagStatus.CLOSED:    ("#444444", "#fff"),
}


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:3px;font-size:11px;font-weight:bold;'
        f'letter-spacing:0.5px;white-space:nowrap">{text.upper()}</span>'
    )


@admin.action(description="Mark selected flags as confirmed")
def mark_confirmed(modeladmin, request, queryset):
    queryset.update(status=FlagStatus.CONFIRMED)


class AuditLogInline(admin.TabularInline):
    model = AuditLog
    extra = 0
    fields = ("timestamp", "actor", "event", "before", "after", "message")
    readonly_fields = ("timestamp", "actor", "event", "before", "after", "message")
    ordering = ("-timestamp",)
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class InspectionInline(admin.TabularInline):
    model = Inspection
    extra = 0
    fields = ("inspector", "verdict", "visited_at", "notes", "submitted_at")
    readonly_fields = ("submitted_at",)
    ordering = ("-submitted_at",)


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "parcel_upi",
        "owner_name",
        "severity_badge",
        "status_badge",
        "confidence_pct",
        "district",
        "assigned_to",
        "created_at",
    )
    list_filter = ("severity", "status", "district")
    search_fields = (
        "detection__parcel__upi",
        "detection__parcel__owner_name",
        "district",
        "notes",
    )
    readonly_fields = ("created_at", "updated_at", "district")
    autocomplete_fields = ("assigned_to",)
    date_hierarchy = "created_at"
    inlines = [InspectionInline, AuditLogInline]
    actions = [mark_confirmed]

    @admin.display(description="Parcel UPI")
    def parcel_upi(self, obj: Flag) -> str:
        if obj.detection.parcel_id:
            return obj.detection.parcel_id
        return "—"

    @admin.display(description="Owner")
    def owner_name(self, obj: Flag) -> str:
        try:
            return obj.detection.parcel.owner_name or "—"
        except Exception:
            return "—"

    @admin.display(description="Severity")
    def severity_badge(self, obj: Flag):
        bg, fg = _SEVERITY_COLOURS.get(obj.severity, ("#888", "#fff"))
        return format_html(_badge(obj.get_severity_display(), bg, fg))

    @admin.display(description="Status")
    def status_badge(self, obj: Flag):
        bg, fg = _STATUS_COLOURS.get(obj.status, ("#888", "#fff"))
        return format_html(_badge(obj.get_status_display(), bg, fg))

    @admin.display(description="Confidence")
    def confidence_pct(self, obj: Flag) -> str:
        try:
            val = obj.detection.confidence
            if val is None:
                return "—"
            return f"{val * 100:.0f}%"
        except Exception:
            return "—"


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("id", "flag", "inspector", "verdict", "visited_at", "submitted_at")
    list_filter = ("verdict",)
    search_fields = ("flag__detection__parcel__upi", "inspector__email", "notes")
    readonly_fields = ("submitted_at",)
    date_hierarchy = "submitted_at"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "flag", "actor", "event", "timestamp")
    list_filter = ("event",)
    search_fields = ("flag__id", "actor__email", "event", "message")
    readonly_fields = ("flag", "actor", "event", "before", "after", "message", "timestamp")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
