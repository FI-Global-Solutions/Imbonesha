import logging

from django.conf import settings

from .base import AbstractNotificationBackend

logger = logging.getLogger(__name__)


class SendGridEmailBackend(AbstractNotificationBackend):
    def __init__(self):
        from sendgrid import SendGridAPIClient

        self._client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        self.from_email = settings.NOTIFICATION_FROM_EMAIL

    def send(self, recipient, subject, body_text, body_html, context=None):
        from sendgrid.helpers.mail import Content, Email, Mail, To

        message = Mail(
            from_email=Email(self.from_email, "Imbonesha"),
            to_emails=To(recipient.email),
            subject=subject,
            plain_text_content=Content("text/plain", body_text),
            html_content=Content("text/html", body_html),
        )
        try:
            response = self._client.send(message)
            logger.info(
                "Email sent to %s: status=%s",
                recipient.email,
                response.status_code,
            )
            return response.status_code in (200, 201, 202)
        except Exception as exc:
            logger.error("SendGrid error sending to %s: %s", recipient.email, exc)
            return False

    def backend_name(self) -> str:
        return "sendgrid_email"
