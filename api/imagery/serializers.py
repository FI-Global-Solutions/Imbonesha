"""Serializers for imagery app."""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import AOI, ImageScene


class AOISerializer(GeoFeatureModelSerializer):
    scene_count = serializers.SerializerMethodField()

    class Meta:
        model = AOI
        geo_field = "boundary"
        fields = ("id", "name", "district", "description", "scene_count", "created_at")

    def get_scene_count(self, obj: AOI) -> int:
        return obj.scenes.count()


class ImageSceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageScene
        fields = ("id", "aoi", "captured_at", "source", "resolution_m", "cog_path", "created_at")
