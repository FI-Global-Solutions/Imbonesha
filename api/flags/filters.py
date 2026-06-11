from django_filters import rest_framework as filters
from .models import Flag


class FlagFilter(filters.FilterSet):
    has_parcel = filters.BooleanFilter(method="filter_has_parcel")
    date_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    status__in = filters.CharFilter(method="filter_status_in")
    permit_status__in = filters.CharFilter(method="filter_permit_status_in")

    def filter_has_parcel(self, queryset, name, value):
        if value is True:
            return queryset.filter(detection__parcel__isnull=False)
        if value is False:
            return queryset.filter(detection__parcel__isnull=True)
        return queryset

    def filter_status_in(self, queryset, name, value):
        statuses = [s.strip() for s in value.split(",") if s.strip()]
        return queryset.filter(status__in=statuses) if statuses else queryset

    def filter_permit_status_in(self, queryset, name, value):
        statuses = [s.strip() for s in value.split(",") if s.strip()]
        return queryset.filter(permit_status__in=statuses) if statuses else queryset

    class Meta:
        model = Flag
        fields = [
            "severity", "status", "district", "permit_status",
            "has_parcel", "date_from", "date_to", "status__in", "permit_status__in",
        ]
