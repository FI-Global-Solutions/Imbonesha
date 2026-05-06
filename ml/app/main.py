"""ML change detection service — FastAPI entry point.

Endpoints:
  GET  /health          — liveness + model status
  POST /detect          — run inference on a T1/T2 image pair
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import settings
from .inference import ChangeDetector

# ---------------------------------------------------------------------------
# Logging — use stdlib integration so structlog works with uvicorn's logger
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.getLevelName(settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# App lifespan — model loaded once at startup
# ---------------------------------------------------------------------------

_detector: ChangeDetector | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _detector
    logger.info("Loading change detection model...")
    _detector = ChangeDetector()
    logger.info(
        "Model ready",
        device=str(_detector.device),
        checkpoint_loaded=_detector.checkpoint_loaded,
    )
    yield
    _detector = None
    logger.info("ML service shut down")


app = FastAPI(
    title="Imbonesha ML Service",
    description="Satellite image change detection for unauthorized building detection",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class DetectRequest(BaseModel):
    t1_path: str = Field(..., description="Absolute path to the T1 (baseline) image on the ml-service filesystem")
    t2_path: str = Field(..., description="Absolute path to the T2 (current) image on the ml-service filesystem")
    aoi_bounds: list[float] | None = Field(
        None,
        description="[west, south, east, north] in WGS84. Used for future tiling; ignored in stub.",
    )
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class PolygonResult(BaseModel):
    polygon: list[list[float]]
    confidence: float
    area_sqm: float


class DetectResponse(BaseModel):
    polygons: list[PolygonResult]
    model_version: str
    inference_ms: float
    checkpoint_loaded: bool


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    model_loaded: bool
    checkpoint_loaded: bool
    device: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _detector is None:
        return HealthResponse(
            status="starting",
            model_loaded=False,
            checkpoint_loaded=False,
            device="unknown",
        )
    return HealthResponse(
        status="ok",
        model_loaded=True,
        checkpoint_loaded=_detector.checkpoint_loaded,
        device=str(_detector.device),
    )


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest) -> DetectResponse:
    if _detector is None:
        raise HTTPException(503, "Model not yet loaded")

    t1 = Path(req.t1_path)
    t2 = Path(req.t2_path)

    if not t1.exists():
        raise HTTPException(422, f"T1 image not found: {t1}")
    if not t2.exists():
        raise HTTPException(422, f"T2 image not found: {t2}")

    logger.info("detect called", t1=str(t1), t2=str(t2))
    t0 = time.perf_counter()

    try:
        polygons = _detector.detect(
            t1_path=t1,
            t2_path=t2,
        )
    except Exception as exc:
        logger.exception("Inference failed", error=str(exc))
        raise HTTPException(500, f"Inference error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    logger.info(
        "detect complete",
        polygons=len(polygons),
        inference_ms=round(elapsed_ms, 1),
    )

    return DetectResponse(
        polygons=[PolygonResult(**p) for p in polygons],
        model_version="siamese-unet-v3",
        inference_ms=round(elapsed_ms, 1),
        checkpoint_loaded=_detector.checkpoint_loaded,
    )
