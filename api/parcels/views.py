"""DRF views for parcels app."""

from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from .models import Parcel
from .serializers import ParcelSerializer


class ParcelViewSet(mixins.RetrieveModelMixin, GenericViewSet):
    queryset = Parcel.objects.prefetch_related("permits")
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated]
    # UPI is the PK
    lookup_field = "upi"
    lookup_value_regex = r"[\w/]+"
