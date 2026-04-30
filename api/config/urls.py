"""URL configuration for Imbonesha API."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from detections.views import DetectionJobViewSet


def health(_request):
    return JsonResponse({"status": "ok", "service": "imbonesha-api"})


router = DefaultRouter()
router.register(r"detection-jobs", DetectionJobViewSet, basename="detection-job")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/v1/", include(router.urls)),
]
