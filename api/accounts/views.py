"""Auth and account views."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


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
