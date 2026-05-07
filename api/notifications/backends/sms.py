from .base import AbstractNotificationBackend


class AfricasTalkingSMSBackend(AbstractNotificationBackend):
    """Stub for Africa's Talking SMS integration.

    Not yet implemented — raises NotImplementedError on any call.
    """

    def send(self, recipient, subject, body_text, body_html, context=None):
        raise NotImplementedError(
            "Africa's Talking SMS backend not yet implemented."
        )

    def backend_name(self) -> str:
        return "africas_talking_sms"
