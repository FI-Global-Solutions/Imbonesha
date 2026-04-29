"""Django signal handlers for the flags app.

The post_save signal on Flag writes an immutable AuditLog row on every
save. We diff the fields that matter for enforcement to keep the log lean.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditLog, Flag

logger = logging.getLogger(__name__)

# Fields whose changes we track in the audit log.
_TRACKED_FIELDS = ("status", "severity", "assigned_to_id", "notes")


@receiver(post_save, sender=Flag)
def flag_post_save(sender, instance: Flag, created: bool, **kwargs) -> None:
    """Write an AuditLog entry whenever a Flag is saved.

    On creation we record the initial values. On update we diff against the
    pre-save snapshot stored on the instance by _flag_pre_save (if present).
    If no snapshot is available (e.g. in tests that skip pre_save), we log
    all current values as 'after'.
    """
    try:
        if created:
            AuditLog.objects.create(
                flag=instance,
                actor=None,  # System-created flags have no human actor.
                event="created",
                before=None,
                after={
                    "status": instance.status,
                    "severity": instance.severity,
                    "assigned_to_id": instance.assigned_to_id,
                },
                message=f"Flag created with severity={instance.severity}",
            )
        else:
            snapshot: dict | None = getattr(instance, "_pre_save_snapshot", None)
            if snapshot:
                changed = {
                    field: {"from": snapshot[field], "to": getattr(instance, field)}
                    for field in _TRACKED_FIELDS
                    if snapshot.get(field) != getattr(instance, field)
                }
                if not changed:
                    return
                AuditLog.objects.create(
                    flag=instance,
                    actor=getattr(instance, "_actor", None),
                    event="updated",
                    before={f: snapshot[f] for f in changed},
                    after={f: getattr(instance, f) for f in changed},
                    message=f"Fields changed: {', '.join(changed)}",
                )
            else:
                AuditLog.objects.create(
                    flag=instance,
                    actor=None,
                    event="updated",
                    before=None,
                    after={
                        "status": instance.status,
                        "severity": instance.severity,
                        "assigned_to_id": instance.assigned_to_id,
                    },
                    message="Flag updated (no pre-save snapshot available)",
                )
    except Exception:
        # Never let audit logging crash the save that triggered it.
        logger.exception("AuditLog write failed for Flag #%s", instance.pk)
