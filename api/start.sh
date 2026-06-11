#!/bin/sh
set -e

echo "=== API: running database migrations ==="
python manage.py migrate --noinput

echo "=== API: collecting static files ==="
python manage.py collectstatic --noinput

echo "=== API: waiting for permit service to be ready ==="
PERMIT_URL="${PERMIT_SERVICE_URL:-http://localhost:8001}"
MAX_ATTEMPTS=12
ATTEMPT=0
until curl -sf "${PERMIT_URL}/health" > /dev/null 2>&1; do
  ATTEMPT=$((ATTEMPT + 1))
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo "WARNING: Permit service not reachable after ${MAX_ATTEMPTS} attempts — skipping parcel sync"
    break
  fi
  echo "  Waiting for permit service... (attempt ${ATTEMPT}/${MAX_ATTEMPTS})"
  sleep 10
done

if curl -sf "${PERMIT_URL}/health" > /dev/null 2>&1; then
  echo "=== API: syncing parcels from permit service ==="
  python manage.py sync_parcels_from_permit_service \
    --service-url "${PERMIT_URL}" \
    --start 1 \
    --end 80
else
  echo "WARNING: Skipped parcel sync (permit service unreachable)"
fi

echo "=== API: starting gunicorn ==="
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120
