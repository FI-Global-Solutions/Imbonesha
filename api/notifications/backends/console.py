import logging

from .base import AbstractNotificationBackend

logger = logging.getLogger(__name__)


class ConsoleBackend(AbstractNotificationBackend):
    def send(self, recipient, subject, body_text, body_html, context=None):
        logger.info(
            "\n===== NOTIFICATION =====\n"
            "To: %s (%s)\n"
            "Subject: %s\n"
            "Body:\n%s\n"
            "========================\n",
            recipient.email,
            recipient.get_full_name(),
            subject,
            body_text,
        )
        return True

    def backend_name(self) -> str:
        return "console"
