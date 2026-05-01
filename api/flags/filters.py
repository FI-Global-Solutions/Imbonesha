from django_filters import rest_framework as filters
from .models import Flag


class FlagFilter(filters.FilterSet):
    has_parcel = filters.BooleanFilter(method="filter_has_parcel")

    def filter_has_parcel(self, queryset, name, value):
        if value is True:
            return queryset.filter(detection__parcel__isnull=False)
        if value is False:
            return queryset.filter(detection__parcel__isnull=True)
        return queryset

    class Meta:
        model = Flag
        fields = ["severity", "status", "district", "has_parcel"]
