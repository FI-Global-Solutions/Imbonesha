"""Auth and account views."""

import hashlib
import random
import string
from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserRole
from .serializers import UserSerializer, InspectorSerializer


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _send_otp_email(user: User, otp: str) -> None:
    from notifications.services import get_backend
    context = {"otp": otp, "user": user}
    body_html = render_to_string("notifications/otp_login.html", context)
    body_text = render_to_string("notifications/otp_login.txt", context)
    backend = get_backend()
    backend.send(
        recipient=user,
        subject="[Imbonesha] Your login code",
        body_text=body_text,
        body_html=body_html,
    )


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


class LoginView(APIView):
    """Step 1 — validate credentials, issue OTP, return otp_required flag."""
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "No active account found with the given credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({"detail": "No active account found with the given credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({"detail": "This account has been deactivated."}, status=status.HTTP_403_FORBIDDEN)

        otp = _generate_otp()
        user.otp_hash = _hash_otp(otp)
        user.otp_expires_at = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=["otp_hash", "otp_expires_at"])

        try:
            _send_otp_email(user, otp)
        except Exception:
            pass  # Log but don't block — console backend used in dev

        return Response({"otp_required": True, "email": email})


class VerifyOtpView(APIView):
    """Step 2 — validate OTP, return JWT tokens."""
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        email = request.data.get("email", "").strip().lower()
        otp = request.data.get("otp", "").strip()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_401_UNAUTHORIZED)

        if (
            not user.otp_hash
            or not user.otp_expires_at
            or user.otp_expires_at < timezone.now()
            or user.otp_hash != _hash_otp(otp)
        ):
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_401_UNAUTHORIZED)

        # Clear OTP so it can't be reused
        user.otp_hash = ""
        user.otp_expires_at = None
        user.save(update_fields=["otp_hash", "otp_expires_at"])

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


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
