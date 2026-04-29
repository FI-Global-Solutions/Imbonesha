"""Django admin for the flags app."""

from django.contrib import admin

from .models import AuditLog, Flag, Inspection


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
        "severity",
        "status",
        "district",
        "assigned_to",
        "created_at",
        "updated_at",
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

    @admin.display(description="Parcel UPI")
    def parcel_upi(self, obj: Flag) -> str:
        if obj.detection.parcel_id:
            return obj.detection.parcel_id
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
