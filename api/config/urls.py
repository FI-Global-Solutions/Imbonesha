"""URL configuration for Imbonesha API."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import MeView
from detections.views import DetectionJobViewSet
from flags.views import AnalyticsView, FlagViewSet, ReportViewSet
from imagery.views import AOIViewSet
from parcels.views import ParcelViewSet


def health(_request):
    return JsonResponse({"status": "ok", "service": "imbonesha-api"})


router = DefaultRouter()
router.register(r"detection-jobs", DetectionJobViewSet, basename="detection-job")
router.register(r"flags", FlagViewSet, basename="flag")
router.register(r"aois", AOIViewSet, basename="aoi")
router.register(r"parcels", ParcelViewSet, basename="parcel")
router.register(r"reports", ReportViewSet, basename="report")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/v1/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/me/", MeView.as_view(), name="me"),
    path("api/v1/analytics/summary/", AnalyticsView.as_view(), name="analytics-summary"),
    path("api/v1/", include(router.urls)),
]
