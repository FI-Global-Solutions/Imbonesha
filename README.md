# Imbonesha

AI-powered detection of unauthorized buildings in Kigali. Compares satellite imagery
across two timestamps, flags new constructions, verifies against the Rwanda Housing
Authority permit registry, and routes findings to district inspectors.

## Repository structure

```
imbonesha/
├── api/                    Django + DRF main platform (auth, flags, inspections, reports)
├── ml/                     PyTorch training + inference for change detection
├── web/                    Next.js admin and inspector dashboard
├── mobile/                 React Native field inspector app
├── mock-services/
│   └── permit-service/     FastAPI mock of the future RHA / KUBAKA integration
├── infra/                  Docker Compose, Kubernetes manifests, deployment scripts
├── docs/                   Architecture, integration contracts, runbooks
└── scripts/                One-off helpers (seed data, dataset prep, etc.)
```

## Quick start

Requirements: Docker Desktop, Python 3.11+, Node 20+, GNU make.

```bash
git clone <repo>
cd imbonesha
make bootstrap     # builds containers, runs migrations, seeds mock data
make up            # starts all services
make seed          # loads mock parcels and permits
```

After `make up`, services are reachable at:

| Service                | URL                              |
|------------------------|----------------------------------|
| Main API (Django)      | http://localhost:8000            |
| Django admin           | http://localhost:8000/admin      |
| Mock permit service    | http://localhost:8001            |
| Web dashboard (Next)   | http://localhost:3000            |
| PostGIS                | localhost:5432 (user: imbonesha) |
| MinIO console          | http://localhost:9001            |

Default admin credentials are seeded: `admin@imbonesha.local` / `changeme`.
**Rotate before any non-local deployment.**

## Documentation

- [Architecture](docs/architecture.md)
- [Getting started](docs/getting-started.md)
- [Integration contract](docs/integration-contract.md) — the spec we'll negotiate
  with the KUBAKA team when real permit data access is granted

## License

Proprietary. Government of Rwanda project.
