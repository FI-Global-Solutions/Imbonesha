from __future__ import annotations

import logging

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def get_backend():
    backend_name = getattr(settings, "NOTIFICATION_BACKEND", "console")
    if backend_name == "sendgrid":
        from .backends.email import SendGridEmailBackend
        return SendGridEmailBackend()
    from .backends.console import ConsoleBackend
    return ConsoleBackend()


def _parcel_context(flag) -> dict:
    """Build parcel context dict, safe for flags with no matched parcel."""
    parcel = flag.detection.parcel if flag.detection else None
    if parcel:
        active_permit = parcel.permits.filter(status="active").first() if hasattr(parcel, "permits") else None
        return {
            "upi": parcel.upi,
            "owner_name": parcel.owner_name,
            "district": parcel.district,
            "sector": parcel.sector,
            "cell": parcel.cell,
            "has_active_permit": active_permit is not None,
        }
    return {
        "upi": "Unregistered parcel",
        "owner_name": "Unknown",
        "district": "Unknown",
        "sector": "",
        "cell": "",
        "has_active_permit": False,
    }


class NotificationService:
    @staticmethod
    def notify_flag_assigned(flag, inspector, assigned_by) -> None:
        """Enqueue a notification to the inspector when a flag is assigned."""
        from .tasks import send_notification_task
        from .models import MobileNotification

        parcel = _parcel_context(flag)
        subject = (
            f"[Imbonesha] New assignment: {parcel['upi']} — {flag.get_severity_display()}"
        )
        context = {
            "flag": flag,
            "inspector": inspector,
            "assigned_by": assigned_by,
            "parcel": parcel,
            "severity": flag.get_severity_display(),
            "dashboard_url": f"{settings.FRONTEND_URL}/assignments",
        }
        body_html = render_to_string("notifications/flag_assigned.html", context)
        body_text = render_to_string("notifications/flag_assigned.txt", context)

        send_notification_task.delay(
            recipient_id=str(inspector.id),
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            notification_type="flag_assigned",
            related_flag_id=flag.id,
        )

        permit_text = "No permit" if not parcel["has_active_permit"] else "Permitted"
        push_body = f"{flag.get_severity_display()} severity · {permit_text}"
        MobileNotification.objects.create(
            recipient=inspector,
            title=f"New assignment: {parcel['upi']}",
            body=push_body,
            notification_type="flag_assigned",
            related_flag=flag,
        )

        if getattr(inspector, "expo_push_token", ""):
            send_notification_task.delay(
                recipient_id=str(inspector.id),
                subject=f"New assignment: {parcel['upi']}",
                body_text=push_body,
                body_html="",
                notification_type="flag_assigned",
                related_flag_id=flag.id,
                backend_override="expo_push",
                task_context={"flag_id": flag.id},
            )

    @staticmethod
    def notify_inspection_complete(flag, inspection) -> None:
        """Enqueue a notification to the assigner when an inspector submits a verdict."""
        if not flag.assigned_by_id:
            return

        from .tasks import send_notification_task

        parcel = _parcel_context(flag)
        subject = (
            f"[Imbonesha] Inspection complete: {parcel['upi']} — "
            f"{inspection.get_verdict_display()}"
        )
        context = {
            "flag": flag,
            "inspection": inspection,
            "inspector": inspection.inspector,
            "verdict": inspection.get_verdict_display(),
            "parcel": parcel,
            "dashboard_url": f"{settings.FRONTEND_URL}/flags",
        }
        body_html = render_to_string("notifications/inspection_complete.html", context)
        body_text = render_to_string("notifications/inspection_complete.txt", context)

        send_notification_task.delay(
            recipient_id=str(flag.assigned_by_id),
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            notification_type="inspection_complete",
            related_flag_id=flag.id,
        )
