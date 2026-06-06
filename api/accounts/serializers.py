"""Serializers for the accounts app."""

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username", "role", "district", "first_name", "last_name")
        read_only_fields = fields


class InspectorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "full_name", "first_name", "last_name",
            "district", "phone_number", "is_active",
        )
        read_only_fields = fields

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.email
