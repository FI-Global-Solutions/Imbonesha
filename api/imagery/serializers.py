"""Serializers for imagery app."""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import AOI, ImageScene


class AOISerializer(GeoFeatureModelSerializer):
    scene_count = serializers.SerializerMethodField()
    latest_scenes = serializers.SerializerMethodField()

    class Meta:
        model = AOI
        geo_field = "boundary"
        fields = ("id", "name", "district", "description", "scene_count", "latest_scenes", "created_at")

    def get_scene_count(self, obj: AOI) -> int:
        return obj.scenes.count()

    def get_latest_scenes(self, obj: AOI) -> list[dict]:
        """Return the two most recent scenes (oldest first = T1, newest = T2)."""
        scenes = obj.scenes.order_by("captured_at")
        if scenes.count() < 2:
            return []
        t1, t2 = scenes.first(), scenes.last()
        return [
            {"id": t1.pk, "captured_at": t1.captured_at, "label": "T1"},
            {"id": t2.pk, "captured_at": t2.captured_at, "label": "T2"},
        ]


class ImageSceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageScene
        fields = ("id", "aoi", "captured_at", "source", "resolution_m", "cog_path", "created_at")
