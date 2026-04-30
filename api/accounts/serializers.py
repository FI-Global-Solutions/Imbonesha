"""Serializers for the accounts app."""

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username", "role", "district", "first_name", "last_name")
        read_only_fields = fields
