"""DRF views for imagery app."""

from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from .models import AOI
from .serializers import AOISerializer


class AOIViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    queryset = AOI.objects.prefetch_related("scenes").order_by("district", "name")
    serializer_class = AOISerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["district"]
    search_fields = ["name", "district"]
