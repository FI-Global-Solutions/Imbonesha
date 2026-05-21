from __future__ import annotations

import logging

import httpx

from .base import AbstractNotificationBackend

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class ExpoPushBackend(AbstractNotificationBackend):
    """Sends push notifications via the Expo Push Notification service."""

    def send(
        self,
        recipient,
        subject: str,
        body_text: str,
        body_html: str,
        context: dict | None = None,
    ) -> bool:
        token = getattr(recipient, "expo_push_token", "")
        if not token:
            logger.info("No push token for %s — skipping push", recipient.email)
            return False

        payload = {
            "to": token,
            "title": subject,
            "body": body_text,
            "sound": "default",
            "priority": "high",
        }
        if context and context.get("flag_id"):
            payload["data"] = {"flagId": context["flag_id"]}

        try:
            resp = httpx.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            # Expo returns a data array — check for errors
            for item in result.get("data", []):
                if item.get("status") == "error":
                    details = item.get("details", {})
                    error_type = details.get("error", "")
                    if error_type == "DeviceNotRegistered":
                        # Token is stale — clear it so we don't retry
                        recipient.expo_push_token = ""
                        recipient.save(update_fields=["expo_push_token"])
                        logger.warning("Cleared stale push token for %s", recipient.email)
                    else:
                        logger.warning("Expo push error for %s: %s", recipient.email, item.get("message"))
                    return False
            return True
        except Exception as exc:
            logger.warning("Expo push failed for %s: %s", recipient.email, exc)
            return False

    def backend_name(self) -> str:
        return "expo_push"
