#!/bin/sh
set -e

echo "=== Permit Service: seeding database ==="
python -m app.seed

echo "=== Permit Service: starting server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8001
