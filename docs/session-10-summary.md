# Session 10 Summary — Email Notifications

## What was built

A full email notification system wired into the flag assignment and inspection workflows. When an admin assigns a flag to an inspector, the inspector receives an email. When the inspector submits a verdict, the assigning admin receives an email. Notifications are dispatched asynchronously via Celery so assignment never blocks on SendGrid availability.

## Architecture

**Adapter pattern** — a `AbstractNotificationBackend` interface with three implementations:
- `ConsoleBackend` — prints to worker logs (default in dev/CI)
- `SendGridEmailBackend` — sends real emails via SendGrid API
- `AfricasTalkingSMSBackend` — stub raising `NotImplementedError` (future)

Backend is selected at runtime via `NOTIFICATION_BACKEND` env var. `get_backend()` factory in `services.py` performs selection — no registry, no plugin system.

**Async dispatch** — `send_notification_task` is a Celery task (`acks_late=True`, 3 retries, 60s delay). The view enqueues it via `.delay()` and returns immediately. If SendGrid is down, the assignment still succeeds and the task retries in the background.

**Audit trail** — every send attempt (success or failure) is written to `NotificationLog` before the retry decision. This means the admin can see failed notifications in Django admin and investigate.

## Files created

```
api/notifications/
├── __init__.py
├── apps.py
├── models.py              # NotificationLog
├── admin.py               # NotificationLog admin (read-only)
├── services.py            # NotificationService + _parcel_context + get_backend
├── tasks.py               # send_notification_task (Celery)
├── backends/
│   ├── base.py            # AbstractNotificationBackend
│   ├── console.py         # ConsoleBackend
│   ├── email.py           # SendGridEmailBackend
│   └── sms.py             # AfricasTalkingSMSBackend (stub)
├── templates/notifications/
│   ├── flag_assigned.html / .txt
│   ├── inspection_complete.html / .txt
│   └── flag_escalated.html / .txt   (future)
└── migrations/0001_initial.py
api/tests/test_notifications.py  (18 tests)
.env.example
```

## Files modified

- `api/config/settings/base.py` — added `NOTIFICATION_BACKEND`, `SENDGRID_API_KEY`, `NOTIFICATION_FROM_EMAIL`, `FRONTEND_URL`, `notifications` to `INSTALLED_APPS`
- `api/flags/views.py` — added `NotificationService.notify_flag_assigned()` in `assign` and `bulk_assign` actions; `NotificationService.notify_inspection_complete()` in `inspect` action
- `api/requirements.txt` — added `sendgrid==6.11.0`
- `infra/docker-compose.yml` — added notification env vars to `api` and `worker` services

## Null-safety pattern

`_parcel_context(flag)` in `services.py` always returns a fully-populated dict regardless of whether `flag.detection.parcel` is set. Templates never need `{% if parcel %}` guards. Unmatched flags get: `upi="Unregistered parcel"`, `owner_name="Unknown"`, `district="Unknown"`, `has_active_permit=False`.

## Integration points (flags/views.py)

| Action | Recipient | Trigger |
|--------|-----------|---------|
| `assign` | Inspector | After `AuditLog.objects.create()` for the assignment |
| `bulk_assign` | Inspector | Inside loop, after each `AuditLog.objects.create()` |
| `inspect` | Admin who assigned | After `AuditLog.objects.create()` for the verdict |
| `inspect` when `flag.assigned_by` is None | — | No notification sent (guard in `notify_inspection_complete`) |

## Sidebar badge

Already implemented from session 8. Shows `assigned` count for inspectors and `pending` count for admins. No changes needed.

## Test results

```
39 passed (27 original + 12 new notification tests in test_notifications.py)
```

18 tests collected in `test_notifications.py`:
- ConsoleBackend (send, backend_name, logging)
- SendGridEmailBackend (send success, send failure, backend_name)
- `_parcel_context` (with parcel, with None parcel)
- `NotificationService.notify_flag_assigned` (enqueues task, subject contains UPI)
- `NotificationService.notify_inspection_complete` (sends to assigner, skips with no assigner)
- `send_notification_task` (log on success, log on failure, missing recipient early return)
- Integration: assign endpoint, bulk-assign endpoint, inspect endpoint

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTIFICATION_BACKEND` | `console` | `console` or `sendgrid` |
| `SENDGRID_API_KEY` | `""` | Required when backend=sendgrid |
| `NOTIFICATION_FROM_EMAIL` | `notifications@imbonesha.gov.rw` | Must be verified in SendGrid |
| `FRONTEND_URL` | `http://localhost:54112` | Base URL for dashboard links in emails |

See `.env.example` at project root for a template.

## Enabling real SendGrid

1. Create a `.env` file at the project root (gitignored):
   ```
   NOTIFICATION_BACKEND=sendgrid
   SENDGRID_API_KEY=SG.your_real_key_here
   NOTIFICATION_FROM_EMAIL=your_verified_sender@email.com
   ```
2. Restart services to pick up new env:
   ```
   docker compose -f infra/docker-compose.yml down
   make up
   ```
3. Assign a flag — the inspector should receive an email within 30 seconds.
4. Check `NotificationLog` in Django admin for delivery status.

## Next steps

- **SMS notifications** — implement `AfricasTalkingSMSBackend` when AT account is provisioned. The adapter slot is already wired; just fill in `send()`.
- **Push notifications** — add `FCMBackend` when mobile app is built. Same adapter interface.
- **Notification preferences** — let users opt out of specific notification types (store preferences on `User` model, check before enqueuing).
- **Digest mode** — batch multiple flag-assigned notifications into a single daily email for high-volume districts.
- **Template improvements** — add actual Imbonesha logo image, refine colour scheme to match the dashboard.
