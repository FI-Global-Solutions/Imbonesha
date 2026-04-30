#!/usr/bin/env bash
# End-to-end demo: seed sample imagery → run detection → print flags.
#
# Usage:
#   ./scripts/demo_e2e.sh                  # seeds + runs full demo
#   ./scripts/demo_e2e.sh <t1_id> <t2_id>  # use existing scene IDs
#
# Requirements:
#   - make up (all containers running)
#   - ml-service healthy (check: curl http://localhost:8002/health)
#
set -euo pipefail

COMPOSE="docker compose -f infra/docker-compose.yml"
API="$COMPOSE exec -T api"
WORKER="$COMPOSE exec -T worker"

# ---------------------------------------------------------------------------
# Step 1: Seed sample scenes (if IDs not provided)
# ---------------------------------------------------------------------------

if [[ $# -ge 2 ]]; then
  T1_ID=$1
  T2_ID=$2
  echo "[demo] Using existing scenes: T1=$T1_ID T2=$T2_ID"
else
  echo "[demo] Seeding sample scenes..."
  SEED_OUTPUT=$($API python manage.py seed_sample_scenes 2>&1)
  echo "$SEED_OUTPUT"

  T1_ID=$(echo "$SEED_OUTPUT" | grep 'T1 scene ID:' | grep -o '[0-9]*$')
  T2_ID=$(echo "$SEED_OUTPUT" | grep 'T2 scene ID:' | grep -o '[0-9]*$')

  if [[ -z "$T1_ID" || -z "$T2_ID" ]]; then
    echo "[error] Could not parse scene IDs from seed output. Check above."
    exit 1
  fi
  echo "[demo] Scenes created: T1=$T1_ID T2=$T2_ID"
fi

# ---------------------------------------------------------------------------
# Step 2: Check ml-service health
# ---------------------------------------------------------------------------

echo ""
echo "[demo] Checking ml-service health..."
ML_HEALTH=$(curl -s http://localhost:8002/health 2>/dev/null || echo '{"status":"unreachable"}')
echo "  ml-service: $ML_HEALTH"

ML_STATUS=$(echo "$ML_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
if [[ "$ML_STATUS" != "ok" && "$ML_STATUS" != "starting" ]]; then
  echo "[warn] ml-service is not healthy. Detection will fall back to error."
  echo "       Run: docker compose -f infra/docker-compose.yml up -d ml-service"
fi

# ---------------------------------------------------------------------------
# Step 3: Trigger detection job via Celery
# ---------------------------------------------------------------------------

echo ""
echo "[demo] Triggering detection job (T1=$T1_ID, T2=$T2_ID)..."

JOB_RESULT=$($API python manage.py shell -c "
import json
from detections.tasks import run_detection_job
from detections.models import DetectionJob

# Run synchronously for the demo (avoids needing worker + broker round-trip).
from imagery.models import ImageScene
from detections.models import DetectionJob, JobStatus
from django.utils import timezone

t1 = ImageScene.objects.get(pk=$T1_ID)
t2 = ImageScene.objects.get(pk=$T2_ID)

job = DetectionJob.objects.create(
    t1_scene=t1,
    t2_scene=t2,
    status=JobStatus.RUNNING,
    model_version='siamese-unet-v0',
    started_at=timezone.now(),
)

from detections.tasks import _run_pipeline
from services.permits import get_permit_adapter
flags_created = _run_pipeline(job)

job.status = JobStatus.COMPLETED
job.ran_at = timezone.now()
job.save(update_fields=['status', 'ran_at'])

print(json.dumps({'job_id': job.pk, 'detections': job.detections.count(), 'flags': flags_created}))
" 2>&1)

echo "  Result: $JOB_RESULT"

JOB_ID=$(echo "$JOB_RESULT" | python3 -c "import sys,json; lines=[l for l in sys.stdin.read().split('\n') if l.startswith('{')]; print(json.loads(lines[-1])['job_id'])" 2>/dev/null || echo "")

if [[ -z "$JOB_ID" ]]; then
  echo "[error] Could not parse job ID. Full output above."
  exit 1
fi

echo "[demo] DetectionJob #$JOB_ID created."

# ---------------------------------------------------------------------------
# Step 4: Print flags with severity, parcel, permit status
# ---------------------------------------------------------------------------

echo ""
echo "[demo] Flags created:"

$API python manage.py shell -c "
from flags.models import Flag, Severity
from detections.models import DetectionJob

job = DetectionJob.objects.get(pk=$JOB_ID)
flags = Flag.objects.filter(detection__job=job).select_related('detection__parcel').order_by('-severity', 'pk')

if not flags.exists():
    print('  (no flags — ml-service may have returned 0 polygons)')
else:
    print(f'  {'Severity':<10} {'Status':<12} {'Parcel UPI':<22} {'District':<12} Confidence')
    print('  ' + '-' * 80)
    for f in flags:
        upi = f.detection.parcel.upi if f.detection.parcel else 'unmatched'
        conf = f'{f.detection.confidence:.3f}' if f.detection.confidence else 'N/A'
        print(f'  {f.severity:<10} {f.status:<12} {upi:<22} {f.district:<12} {conf}')
    print()
    by_sev = {}
    for f in flags:
        by_sev.setdefault(f.severity, 0)
        by_sev[f.severity] += 1
    print('  Summary:')
    for sev in ['critical', 'high', 'medium', 'low']:
        if sev in by_sev:
            print(f'    {sev.upper()}: {by_sev[sev]}')
"

echo ""
echo "[demo] Done. Django admin: http://localhost:8007/admin"
