.PHONY: help bootstrap up down logs seed test lint clean reset

help:
	@echo "Imbonesha development commands"
	@echo ""
	@echo "  make bootstrap   Build images, run migrations, create superuser, seed data"
	@echo "  make up          Start all services (detached)"
	@echo "  make down        Stop all services"
	@echo "  make logs        Tail logs from all services"
	@echo "  make seed        Re-seed mock parcels and permits"
	@echo "  make test        Run all test suites"
	@echo "  make lint        Run linters across all services"
	@echo "  make shell-api   Open a shell in the api container"
	@echo "  make shell-db    Open a psql shell in PostGIS"
	@echo "  make reset       Nuke volumes and rebuild from scratch"

bootstrap:
	docker compose -f infra/docker-compose.yml build
	docker compose -f infra/docker-compose.yml up -d db minio
	@echo "Waiting for database..."
	@sleep 5
	docker compose -f infra/docker-compose.yml run --rm api python manage.py migrate
	docker compose -f infra/docker-compose.yml run --rm api python manage.py createsuperuser_if_none
	$(MAKE) seed
	@echo ""
	@echo "Bootstrap complete. Run 'make up' to start all services."

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f --tail=100

seed:
	docker compose -f infra/docker-compose.yml run --rm api python manage.py seed_mock_parcels
	docker compose -f infra/docker-compose.yml run --rm permit-service python -m app.seed

test:
	docker compose -f infra/docker-compose.yml run --rm api pytest
	docker compose -f infra/docker-compose.yml run --rm permit-service pytest

lint:
	docker compose -f infra/docker-compose.yml run --rm api ruff check .
	docker compose -f infra/docker-compose.yml run --rm permit-service ruff check .

shell-api:
	docker compose -f infra/docker-compose.yml exec api python manage.py shell

shell-db:
	docker compose -f infra/docker-compose.yml exec db psql -U imbonesha -d imbonesha

reset:
	docker compose -f infra/docker-compose.yml down -v
	$(MAKE) bootstrap
