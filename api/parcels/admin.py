"""Admin registrations for parcels and permits.

Read-only-ish: parcels and permits are sourced from the external registry,
so editing them in admin doesn't actually update the source. We allow
edits anyway for emergency local overrides during demos, but display a
warning on the change form.
"""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Parcel, Permit


class PermitInline(admin.TabularInline):
    model = Permit
    extra = 0
    fields = ("permit_no", "category", "status", "issued_date", "expiry_date", "intended_use")
    readonly_fields = ("last_synced_at",)


@admin.register(Parcel)
class ParcelAdmin(GISModelAdmin):
    list_display = (
        "upi",
        "owner_name",
        "district",
        "sector",
        "land_use",
        "zone_type",
        "has_active_permit",
        "last_synced_at",
    )
    list_filter = ("district", "sector", "land_use", "zone_type")
    search_fields = ("upi", "owner_name", "cell")
    readonly_fields = ("last_synced_at",)
    inlines = [PermitInline]

    @admin.display(boolean=True, description="Active permit?")
    def has_active_permit(self, obj: Parcel) -> bool:
        return obj.has_active_permit


@admin.register(Permit)
class PermitAdmin(admin.ModelAdmin):
    list_display = (
        "permit_no",
        "parcel",
        "category",
        "status",
        "intended_use",
        "issued_date",
        "expiry_date",
    )
    list_filter = ("status", "category", "intended_use")
    search_fields = ("permit_no", "parcel__upi", "applicant_name")
    readonly_fields = ("last_synced_at",)
    autocomplete_fields = ("parcel",)
