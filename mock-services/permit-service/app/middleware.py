"""Latency and error injection middleware.

Real government APIs in Rwanda are slow (300-1000ms typical) and occasionally
return 5xx errors. By forcing these conditions in development, we ensure the
main API has retry logic, caching, and graceful degradation built in from
day one — instead of discovering all this when we go live.

This is a critical piece of the mock. Do not disable it without good reason.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)


class RealisticConditionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip latency injection on health checks and docs.
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Inject latency.
        if settings.inject_latency_ms > 0:
            jitter = random.randint(0, settings.inject_latency_jitter_ms)
            delay_ms = settings.inject_latency_ms + jitter
            await asyncio.sleep(delay_ms / 1000)

        # Inject errors. The real KUBAKA will not be 100% available — neither
        # is our mock.
        if settings.error_rate > 0 and random.random() < settings.error_rate:
            logger.info(
                "Injected 503 error on %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "detail": "Upstream registry temporarily unavailable. Retry with backoff.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                headers={"Retry-After": "2"},
            )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.0f}"
        return response
