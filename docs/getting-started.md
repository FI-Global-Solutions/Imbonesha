# Getting started

This guide walks a new developer from a fresh `git clone` to a running local
environment and a successful API call against the mock permit service.

## Prerequisites

| Tool              | Version          | Install                                    |
|-------------------|------------------|--------------------------------------------|
| Docker Desktop    | 4.30+            | https://docs.docker.com/desktop/install/mac-install/ |
| Python            | 3.11+            | `brew install python@3.11`                 |
| Node              | 20+              | `brew install node`                        |
| GNU Make          | any              | comes with macOS                           |
| jq (optional)     | any              | `brew install jq` — pretty JSON in curl    |

Allocate at least 8 GB of RAM and 4 CPUs to Docker Desktop. The AI services
will need more later, but this is enough for the platform layer.

## First-time setup

```bash
git clone <repo-url> imbonesha
cd imbonesha
make bootstrap
```

`make bootstrap` does the following:

1. Builds the Docker images for the api, worker, and permit-service
2. Starts the PostGIS and MinIO containers
3. Runs Django migrations against the main database
4. Seeds 80 mock parcels into the permit-mock database
5. Creates a default Django superuser if none exists

This takes about 3-5 minutes on first run.

## Starting and stopping

```bash
make up        # start all services (detached)
make logs      # tail all logs
make down      # stop everything (data preserved)
make reset     # nuke all volumes and re-bootstrap
```

## Verifying it works

After `make up`, try the mock permit service:

```bash
# Lookup a parcel that has an active permit (authorized scenario)
curl http://localhost:8001/api/v1/parcels/1/01/03/05/0001 | jq

# Lookup a parcel with no permit (the primary "flag this" case)
curl http://localhost:8001/api/v1/parcels/1/01/03/05/0051 | jq

# Lookup a parcel with an expired permit
curl http://localhost:8001/api/v1/parcels/1/01/03/05/0071 | jq

# Lookup by coordinates (somewhere in the seeded grid)
curl "http://localhost:8001/api/v1/parcels-lookup?lat=-1.9418&lng=30.0908" | jq

# Try a UPI that doesn't exist (should return 404)
curl -i http://localhost:8001/api/v1/parcels/9/99/99/99/9999
```

Visit the auto-generated API docs at http://localhost:8001/docs.

## Understanding the seed data

The mock permit service seeds 80 parcels in a 10×8 grid covering roughly
1 km² in Kacyiru sector, Gasabo district, Kigali. The location is real
but the parcels and owner names are entirely fictional.

Each parcel falls into one of four scenarios:

| Scenario        | UPIs              | Behavior |
|-----------------|-------------------|----------|
| authorized      | 0001 — 0048 (60%) | Active permit, all good |
| no_permit       | 0049 — 0064 (20%) | No permit at all — primary flag case |
| expired         | 0065 — 0072 (10%) | Had a permit, lapsed |
| wrong_category  | 0073 — 0080 (10%) | Permit for residential, building looks commercial |

This deterministic distribution is intentional: when demoing to RHA, you
can predictably show a clean parcel, then a problem parcel, then explain
the AI's role in surfacing the difference.

## When latency or 503 errors look "wrong"

The mock injects 300-500ms of latency on every request and returns 503
on roughly 5% of requests. This is intentional — it forces us to build
proper retry and caching logic against realistic government API
conditions. If you need to disable it temporarily for debugging, set
`INJECT_LATENCY_MS=0` and `ERROR_RATE=0` in your local environment.

## Troubleshooting

**`make bootstrap` fails on the seed step.** Wait 10 seconds and run
`make seed` again. PostGIS sometimes takes a moment to be ready.

**`Address already in use` on port 5432, 8000, 8001, or 9000.** You have
another service running on the same port. Either stop it or change the
port mapping in `infra/docker-compose.yml`.

**Docker is using too much RAM.** Restart Docker Desktop. Containers
sometimes leak memory during long dev sessions.

**My changes aren't reflected.** The api and permit-service mount the
source code as a volume, so changes should hot-reload. If they don't,
the worker (Celery) does *not* hot-reload — restart it with
`docker compose -f infra/docker-compose.yml restart worker`.
