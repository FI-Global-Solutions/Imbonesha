import logging

from celery import shared_task

from .services import get_backend

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    name="notifications.send_notification",
)
def send_notification_task(
    self,
    recipient_id: str,
    subject: str,
    body_text: str,
    body_html: str,
    notification_type: str,
    related_flag_id: str | None = None,
) -> dict:
    from accounts.models import User
    from .models import NotificationLog

    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        logger.error("Notification recipient %s not found — dropping task", recipient_id)
        return {"success": False, "reason": "recipient_not_found"}

    backend = get_backend()
    success = backend.send(
        recipient=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )

    NotificationLog.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        backend=backend.backend_name(),
        subject=subject,
        success=success,
        related_flag_id=related_flag_id,
    )

    if not success:
        raise self.retry(exc=Exception(f"Notification send failed for {recipient.email}"))

    return {"success": True, "recipient": recipient.email, "type": notification_type}
