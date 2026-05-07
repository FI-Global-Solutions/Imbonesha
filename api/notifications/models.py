import uuid

from django.db import models
from django.conf import settings


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
