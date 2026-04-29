"""Django admin for the imagery app."""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import AOI, ImageScene


class ImageSceneInline(admin.TabularInline):
    model = ImageScene
    extra = 0
    fields = ("captured_at", "source", "resolution_m", "cog_path", "checksum", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-captured_at",)


@admin.register(AOI)
class AOIAdmin(GISModelAdmin):
    list_display = ("name", "district", "scene_count", "created_at")
    list_filter = ("district",)
    search_fields = ("name", "district", "description")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ImageSceneInline]

    @admin.display(description="Scenes")
    def scene_count(self, obj: AOI) -> int:
        return obj.scenes.count()


@admin.register(ImageScene)
class ImageSceneAdmin(admin.ModelAdmin):
    list_display = ("__str__", "aoi", "source", "resolution_m", "captured_at", "created_at")
    list_filter = ("source", "aoi__district")
    search_fields = ("aoi__name", "cog_path", "checksum")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("aoi",)
    date_hierarchy = "captured_at"
