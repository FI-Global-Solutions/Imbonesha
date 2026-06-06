from rest_framework.pagination import PageNumberPagination


class FlexiblePageNumberPagination(PageNumberPagination):
    """Respects a `limit` query param up to max 1000, default page size 25."""
    page_size = 25
    page_size_query_param = "limit"
    max_page_size = 1000
