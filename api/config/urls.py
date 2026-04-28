"""URL configuration for Imbonesha API.

Currently minimal — the actual API routes will be added in the next session
when we build the auth, flags, and inspections apps.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(_request):
    return JsonResponse({"status": "ok", "service": "imbonesha-api"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
]
