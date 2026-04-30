"""Serializers for parcels app."""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Parcel, Permit


class PermitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permit
        fields = (
            "permit_no", "category", "status", "issued_date", "expiry_date",
            "intended_use", "max_floors_allowed", "max_footprint_sqm", "applicant_name",
        )


class ParcelSerializer(GeoFeatureModelSerializer):
    permits = PermitSerializer(many=True, read_only=True)
    active_permit = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        geo_field = "boundary"
        fields = (
            "upi", "owner_name", "land_use", "district", "sector", "cell",
            "zone_type", "max_floors_allowed_by_zone", "permits", "active_permit",
        )

    def get_active_permit(self, obj: Parcel) -> dict | None:
        permit = obj.permits.filter(status="active").order_by("-issued_date").first()
        if permit is None:
            return None
        return PermitSerializer(permit).data
