"""DRF serializers for the detections app."""

from __future__ import annotations

from rest_framework import serializers

from imagery.models import ImageScene
from .models import DetectionJob, JobStatus


class DetectionJobSerializer(serializers.ModelSerializer):
    t1_scene_id = serializers.IntegerField(source="t1_scene.pk", read_only=True)
    t2_scene_id = serializers.IntegerField(source="t2_scene.pk", read_only=True)
    aoi_name = serializers.CharField(source="t1_scene.aoi.name", read_only=True)
    detection_count = serializers.SerializerMethodField()

    class Meta:
        model = DetectionJob
        fields = [
            "id",
            "t1_scene_id",
            "t2_scene_id",
            "aoi_name",
            "status",
            "model_version",
            "detection_count",
            "started_at",
            "ran_at",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields

    def get_detection_count(self, obj: DetectionJob) -> int:
        return obj.detections.count()


class DetectionJobCreateSerializer(serializers.Serializer):
    t1_scene_id = serializers.IntegerField()
    t2_scene_id = serializers.IntegerField()

    def validate_t1_scene_id(self, value: int) -> int:
        if not ImageScene.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"ImageScene {value} does not exist.")
        return value

    def validate_t2_scene_id(self, value: int) -> int:
        if not ImageScene.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"ImageScene {value} does not exist.")
        return value

    def validate(self, data: dict) -> dict:
        if data["t1_scene_id"] == data["t2_scene_id"]:
            raise serializers.ValidationError("t1_scene_id and t2_scene_id must differ.")

        t1 = ImageScene.objects.select_related("aoi").get(pk=data["t1_scene_id"])
        t2 = ImageScene.objects.select_related("aoi").get(pk=data["t2_scene_id"])
        if t1.aoi_id != t2.aoi_id:
            raise serializers.ValidationError(
                "Both scenes must belong to the same AOI."
            )
        if t1.captured_at >= t2.captured_at:
            raise serializers.ValidationError(
                "t1_scene must be captured before t2_scene."
            )
        return data
