"""DRF views for mobile notifications."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MobileNotification


class MobileNotificationSerializer(serializers.ModelSerializer):
    related_flag_id = serializers.PrimaryKeyRelatedField(
        source="related_flag", read_only=True
    )

    class Meta:
        model = MobileNotification
        fields = [
            "id",
            "title",
            "body",
            "notification_type",
            "related_flag_id",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = MobileNotification.objects.filter(recipient=request.user)
        if request.query_params.get("unread_only") == "true":
            qs = qs.filter(is_read=False)
        # Simple pagination: page_size param, default 50
        try:
            page_size = min(int(request.query_params.get("page_size", 50)), 200)
        except (ValueError, TypeError):
            page_size = 50
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except (ValueError, TypeError):
            page = 1
        offset = (page - 1) * page_size
        total = qs.count()
        results = qs[offset : offset + page_size]
        return Response(
            {
                "count": total,
                "results": MobileNotificationSerializer(results, many=True).data,
            }
        )


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        count = MobileNotification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({"count": count})


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk: str) -> Response:
        try:
            notif = MobileNotification.objects.get(pk=pk, recipient=request.user)
        except MobileNotification.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=["is_read", "read_at"])
        return Response(MobileNotificationSerializer(notif).data)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        marked = MobileNotification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({"marked": marked})
