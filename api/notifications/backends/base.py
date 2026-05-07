from abc import ABC, abstractmethod


class AbstractNotificationBackend(ABC):
    @abstractmethod
    def send(
        self,
        recipient,
        subject: str,
        body_text: str,
        body_html: str,
        context: dict | None = None,
    ) -> bool:
        """Send a notification. Returns True on success."""
        ...

    @abstractmethod
    def backend_name(self) -> str:
        """e.g., 'sendgrid_email', 'africas_talking_sms', 'console'"""
        ...
