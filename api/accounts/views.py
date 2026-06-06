"""Auth and account views."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User, UserRole
from .serializers import UserSerializer, InspectorSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class PushTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)
        request.user.expo_push_token = token
        request.user.save(update_fields=["expo_push_token"])
        return Response({"registered": True})

    def delete(self, request: Request) -> Response:
        request.user.expo_push_token = ""
        request.user.save(update_fields=["expo_push_token"])
        return Response({"registered": False})


class InspectorListView(APIView):
    """List all inspectors. Admin sees all; district_admin sees their district only."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if user.role not in {UserRole.ADMIN, UserRole.DISTRICT_ADMIN}:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        qs = User.objects.filter(role=UserRole.INSPECTOR).order_by("first_name", "last_name", "email")
        if user.role == UserRole.DISTRICT_ADMIN and user.district:
            qs = qs.filter(district=user.district)

        return Response(InspectorSerializer(qs, many=True).data)


class InspectorToggleActiveView(APIView):
    """Activate or deactivate an inspector account."""
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk: int) -> Response:
        user = request.user
        if user.role not in {UserRole.ADMIN, UserRole.DISTRICT_ADMIN}:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        try:
            inspector = User.objects.get(pk=pk, role=UserRole.INSPECTOR)
        except User.DoesNotExist:
            return Response({"detail": "Inspector not found."}, status=status.HTTP_404_NOT_FOUND)

        if user.role == UserRole.DISTRICT_ADMIN and inspector.district != user.district:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        inspector.is_active = not inspector.is_active
        inspector.save(update_fields=["is_active"])
        return Response(InspectorSerializer(inspector).data)
