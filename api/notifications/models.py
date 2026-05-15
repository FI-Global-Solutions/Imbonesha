import uuid

from django.db import models
from django.conf import settings


class MobileNotification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_notifications",
    )
    title = models.CharField(max_length=255)
    body = models.CharField(max_length=500)
    notification_type = models.CharField(max_length=64)
    related_flag = models.ForeignKey(
        "flags.Flag",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mobile_notifications",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_mobile"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
        ]

    def __str__(self) -> str:
        status = "read" if self.is_read else "unread"
        return f"[{status}] {self.title} → {self.recipient.email}"


class NotificationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=64)
    backend = models.CharField(max_length=64)
    subject = models.CharField(max_length=512)
    success = models.BooleanField()
    related_flag_id = models.BigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["notification_type"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.notification_type} → {self.recipient.email} ({self.backend})"
