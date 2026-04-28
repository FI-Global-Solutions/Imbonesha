# Architecture

Living reference document for the Imbonesha system. Updated as decisions
are made.

## High-level

Imbonesha is composed of independently-deployable services that communicate
through HTTP and a shared PostgreSQL/PostGIS database. All services run in
Docker containers, orchestrated by Docker Compose locally and Kubernetes
in production.

| Service          | Tech                  | Purpose                                  |
|------------------|------------------------|------------------------------------------|
| api              | Django 5 + DRF         | Auth, flags, inspections, reports, admin |
| worker           | Celery + Redis         | Async detection jobs, report generation |
| permit-service   | FastAPI                | Mock of KUBAKA permit API (dev only)     |
| ml-service       | FastAPI + PyTorch      | Change detection inference (Phase 2)     |
| web              | Next.js 14 + Tailwind  | Admin and inspector dashboard            |
| mobile           | React Native           | Field inspector app (Phase 6)            |

## Why Django for the platform

The main API uses Django + Django REST Framework rather than FastAPI for
three reasons specific to this project:

1. **Free admin panel.** Inspectors, parcels, permits, AOIs, master plan
   zones all need CRUD interfaces. Django's admin saves weeks.
2. **First-class PostGIS via `django-rest-framework-gis`.** Geometry fields
   serialize to GeoJSON automatically.
3. **Audit-friendly signals.** Every model state transition can hook into
   `pre_save` / `post_save` to write to `audit_logs`, which we need for
   legal admissibility of flag reports.

For the narrow microservices (mock permits, ML inference), FastAPI's
lower overhead and async-native model is a better fit.

## Data flow for a single detection

```
1. Admin uploads T2 GeoTIFF for an AOI via the dashboard
2. api stores file in MinIO, writes ImageScene row in PostGIS
3. api enqueues a DetectionJob (Celery) with t1_scene_id and t2_scene_id
4. worker:
   a. Pulls both scenes from MinIO
   b. Co-registers and normalizes (AROSICS + histogram matching)
   c. Calls ml-service via HTTP for change detection inference
   d. Receives change polygons, runs building-aware filter
   e. For each new building polygon:
      - Spatial join against PARCELS in main DB → matched UPI
      - HTTP call to permit-service (or real KUBAKA) for permit status
      - Severity scored by area + zone conflict + permit gap
      - Detection row written, Flag row created
      - Notification dispatched (email now, SMS later)
5. Inspector sees flag in dashboard queue
6. Inspector visits site (mobile app), submits verdict
7. Admin exports flag report (PDF + CSV) for enforcement action
```

## Database

PostgreSQL 16 + PostGIS 3.4. Two logical databases on the same instance:

- `imbonesha` — the main app database
- `permit_mock` — the mock permit service database

In production, `permit_mock` goes away — the real KUBAKA adapter calls
out to the actual KUBAKA API instead of our mock.

Spatial indexes are GIST on every geometry column. Critical for parcel
lookups by coordinates which would otherwise full-scan.

## Adapter pattern for permit verification

The main API never talks to the permit-service or KUBAKA directly. It
talks to a `PermitVerificationService` interface that has two
implementations:

- `MockPermitAdapter` — calls our local FastAPI mock (dev / MVP demos)
- `KubakaPermitAdapter` — calls real KUBAKA API (production, future)

Switching is a one-line config change. See `api/services/permits/`.

This pattern is also why `docs/integration-contract.md` exists: it
specifies the interface both adapters must satisfy.

## Authentication

JWT-based, using `djangorestframework-simplejwt`. Roles:

| Role            | Permissions                                              |
|-----------------|----------------------------------------------------------|
| admin           | Full access, can manage AOIs and users                   |
| rha_officer     | Read-only oversight, can export reports                  |
| district_admin  | Manage flags within assigned district only              |
| inspector       | View assigned flags, submit verdicts via mobile app     |
| read_only       | View dashboard, no actions                               |

Role enforcement is in DRF permission classes plus row-level filtering
on querysets — a district admin literally cannot fetch flags from
districts they don't manage.

## Audit log

Every state transition on a Flag, Inspection, or Permit lookup writes
an immutable row to `audit_logs`. The table is append-only at the
application layer; in production we'll also use Postgres row-level
security to prevent UPDATE and DELETE on this table even from
privileged accounts.

## Deferred decisions

The following are deliberately not pinned yet — we'll decide when we
hit them:

- **Imagery cost model**: Planet vs Maxar vs drone — needs vendor pricing
  conversations and AOI-size analysis.
- **Production hosting**: AWS Cape Town vs on-premise vs Rwanda's national
  data center — depends on RHA / RISA security requirements.
- **Notification provider**: Africa's Talking is the obvious choice for
  SMS, but we'll confirm pricing and reliability when we get there.
- **Mobile framework**: React Native is the working assumption but
  Flutter is an option if the team prefers.
