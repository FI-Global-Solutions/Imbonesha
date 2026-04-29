# Session 3 Summary

**Date:** 2026-04-29  
**Goal:** Replace the stub Celery detection task with a real ML inference pipeline.

---

## What Shipped

### ML Service (`ml/`)

- **`ml/app/main.py`** — FastAPI service with `/health` and `/detect` endpoints. Model is loaded once on startup and held in memory. `checkpoint_loaded: false` when no `.pth` file is present (safe — runs with random weights for structure testing).
- **`ml/app/inference.py`** — `SiameseUNet`: a compact (base_ch=32) Siamese U-Net that encodes T1 and T2 with shared weights, diffs features at three scales, and decodes to a per-pixel change probability. `ChangeDetector.detect()` runs the forward pass, thresholds at 0.5, polygonizes with `rasterio.features.shapes`, and filters by area (50–10 000 sqm).
- **`ml/app/preprocessing.py`** — `prepare_pair()`: loads image pair, resizes to 256×256, histogram-matches T2 to T1, generates a cloud/shadow mask. Pure-numpy, no GDAL required for basic images.
- **`ml/app/config.py`** — Pydantic-settings config (checkpoint path, threshold, area bounds).
- **`ml/scripts/train.py`** — Full training loop: `SyntheticChangeDataset` (512 pairs with random bright rectangles = "buildings") + `LevirCDDataset` (for real data). Trains with BCE + Dice loss, AdamW, cosine LR schedule. Saves best checkpoint by val IoU.
- **`ml/scripts/download_levir.py`** — Streams LEVIR-CD splits from Hugging Face, unzips, prints summary.
- **`ml/Dockerfile`** — `python:3.11-slim` + GDAL + PyTorch 2.4.1 CPU wheels + all deps. Build verified on ARM64 (Apple Silicon Docker).
- **`ml/requirements.txt`** — Pinned deps for the ML service.
- **`ml/.dockerignore`** — Excludes data/, scripts/, sample_imagery/ from build context.

### Detection Pipeline (`api/detections/tasks.py`)

Replaced 6 hardcoded `_STUB_FOOTPRINTS` with a real pipeline:

1. **`_download_scene()`** — Downloads from MinIO or falls back to local file path (for volume-mounted sample imagery).
2. **`_call_ml_service()`** — POSTs `{t1_path, t2_path, threshold}` to `ml-service/detect`. Retried 3× with exponential backoff (2–30s) on network errors via tenacity. Hard timeout 5 minutes.
3. **`_pixel_polygon_to_wgs84()`** — Converts pixel-space polygon coordinates to WGS84 using an affine transform stored in `ImageScene.metadata.geo_transform`. Falls back to a nominal 2 m/px transform at Kacyiru's coordinates.
4. All downstream logic unchanged: spatial join → permit adapter → `compute_severity` → `Flag.get_or_create`.

### Sample Imagery (`api/imagery/management/commands/seed_sample_scenes.py`)

Management command that:
- Generates two 256×256 synthetic PNG images (T1: baseline vegetation, T2: T1 + grey rectangles at the 4 scenario parcel locations).
- Writes them to `ml/sample_imagery/` (mounted at `/ml_imagery` in the worker, `/app/sample_imagery` in the ml-service).
- Uploads to MinIO under `sample/kacyiru/...`.
- Creates AOI + T1/T2 `ImageScene` rows with the geo-transform embedded in `ImageScene.metadata`.

### Infrastructure

- `infra/docker-compose.yml` — Added `ml-service` on port 8002, with volume mounts for `ml/app/` (live reload) and `ml/sample_imagery/` (shared imagery). Added `ML_SERVICE_URL` env var to `api` and `worker` services. Added `../ml/sample_imagery:/ml_imagery:ro` to worker volume mounts.
- `api/config/settings/base.py` — Added `ML_SERVICE_URL` setting.
- `api/imagery/models.py` — Added `ImageScene.metadata` JSONField for geo-transform and other scene-level metadata.
- Migration `imagery/migrations/0002_add_imagescene_metadata.py` applied.

### Demo Script (`scripts/demo_e2e.sh`)

End-to-end demo: seeds sample scenes → runs `_run_pipeline()` synchronously → prints a formatted flag table with severity, parcel UPI, and confidence.

### Tests (`api/tests/test_e2e_detection.py`)

Expanded from 4 → 7 tests. Updated to patch both `_call_ml_service` (returns 6 fake polygons keyed to the seeded parcels) and the permit adapter. Uses a `_TEST_TRANSFORM` that maps pixel coords 1:1 to WGS84 degrees so the spatial join still resolves correctly. All 7 pass in ~2.8s.

---

## What's Stubbed / Known Limitations

1. **No trained checkpoint.** The model runs with random weights until someone runs `ml/scripts/train.py`. Random weights produce noisy change probability maps — the `detect` endpoint returns polygons, but they won't correspond to real buildings. The pipeline is end-to-end correct; accuracy waits on a trained model.

2. **`change_type` is always `NEW_BUILDING`.** The ml-service `DetectResponse` doesn't include a `change_type` field per polygon. The `wrong_category` scenario (permit for residential, building looks commercial) therefore gets severity `LOW` (has active permit + new_building) instead of `MEDIUM`. Session 4 should add `change_type` to the ml-service response and propagate it into the pipeline.

3. **No AROSICS co-registration.** `preprocessing.py` applies histogram matching but not the AROSICS geometric co-registration listed in the design doc. Heavy C++ dependency — deferred to when we have real imagery.

4. **Cloud/shadow mask is a brightness heuristic.** Good enough for the synthetic demo; should be replaced with `s2cloudless` for production Sentinel-2 imagery.

5. **Pixel → WGS84 projection requires `ImageScene.metadata.geo_transform`.** For real satellite imagery (Planet, Maxar), this should be read from the GeoTIFF affine transform via rasterio, not embedded in the database. The current fallback (nominal 2 m/px at Kacyiru's origin) is wrong for any imagery not centred on that origin.

6. **`seed_sample_scenes` imagery path is `/ml_imagery` inside the worker.** This requires the `../ml/sample_imagery:/ml_imagery:ro` volume mount in docker-compose. When triggering jobs via the Celery worker (not the demo script's synchronous path), the worker must have this mount. Confirmed in docker-compose.yml.

7. **No checkpoint committed.** `*.pth` is in `.gitignore`. To recreate: `python ml/scripts/train.py --synthetic --epochs 5`. On CPU this takes ~5 minutes. Document this in the ML README.

---

## What Surprised Me

- **`rasterio==1.3.11` fails to build on Python 3.11-slim** because the new pip dropped `pkg_resources` from the default build shim. Fixed by upgrading setuptools before the requirements install, and loosening to `rasterio>=1.3.11` so pip picks `1.4.4` which has a pre-built ARM64 wheel.
- **structlog's `add_logger_name` processor requires a stdlib logger.** When configured with the default `PrintLogger`, it crashes on `logger.name`. Fixed by using `structlog.stdlib.LoggerFactory()` + `LoggerFactory` integration.
- **Pydantic v2 reserves `model_*` field names.** `HealthResponse.model_loaded` triggers a warning that becomes an error in strict mode. Fixed with `ConfigDict(protected_namespaces=())`.
- **Django GEOS `Polygon[0]` vs Shapely `Polygon.exterior`.** The test used `.exterior.coords` on a `django.contrib.gis.geos.Polygon`, which doesn't have that attribute. Django GEOSGeometry rings are accessed via index (`poly[0]`).

---

## Session 4 Recommendations

In priority order:

1. **Train on real data.** Download LEVIR-CD (`python ml/scripts/download_levir.py`), train for 10 epochs (`python ml/scripts/train.py --data-dir ml/data/LEVIR-CD`), commit the checkpoint via Git LFS or a model registry.
2. **Add `change_type` to ml-service response.** Emit per-polygon change type (new_building / extension / demolition / commercial) from the model head or a separate classifier. Wire it into `tasks.py` so `wrong_category` flags get `MEDIUM` severity.
3. **Read geo-transform from GeoTIFF header.** In `_pixel_polygon_to_wgs84`, fall back to reading the rasterio transform from the downloaded file when `metadata.geo_transform` is absent.
4. **DRF REST API for detection jobs.** Currently jobs are triggered via Django shell or the demo script. Add `POST /api/v1/detection-jobs/` (authenticated) so the web dashboard can trigger runs.
5. **Celery beat schedule for nightly parcel sync.** `sync_parcels_from_permit_service` should run automatically every night.
6. **AROSICS co-registration.** Add as an optional step in `preprocessing.py` gated behind `ENABLE_COREGISTRATION=true` so it can be enabled once the full imagery pipeline is tested.
