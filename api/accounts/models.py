"""Custom User model with role-based access control.

Roles map to actual job functions in the Imbonesha workflow:

    admin           Full access, manages AOIs, users, system config
    rha_officer     Oversight role, read-only across all districts, exports
    district_admin  Manages flags within their assigned district only
    inspector       Field worker, sees assigned flags, submits verdicts
    read_only       Dashboard viewer, no actions

Row-level filtering by district is enforced in DRF querysets — a district
admin literally cannot fetch flags from districts they don't manage. See
flags/permissions.py.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    RHA_OFFICER = "rha_officer", "RHA Officer"
    DISTRICT_ADMIN = "district_admin", "District Admin"
    INSPECTOR = "inspector", "Inspector"
    READ_ONLY = "read_only", "Read Only"


class User(AbstractUser):
    # Email is the canonical identifier — usernames cause friction in
    # every government project we've researched.
    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=32,
        choices=UserRole.choices,
        default=UserRole.READ_ONLY,
    )

    # For district_admin and inspector roles, restrict their work to a
    # specific district. Empty string means "all districts" (admin / rha_officer).
    district = models.CharField(max_length=64, blank=True, default="")

    phone_number = models.CharField(max_length=32, blank=True, default="")

    expo_push_token = models.CharField(max_length=200, blank=True, default="")

    USERNAME_FIELD = "email"
    # `username` stays in REQUIRED_FIELDS for compatibility with createsuperuser.
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "accounts_user"
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["district"]),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_district_scoped(self) -> bool:
        """True if this user's view should be filtered to their district."""
        return self.role in {UserRole.DISTRICT_ADMIN, UserRole.INSPECTOR}
