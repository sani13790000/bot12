"""Observability middleware for Galaxy Vast AI Trading Platform.

Provides per-request:
- Correlation ID injection (X-Request-ID header)
- Structured access logging
- Prometheus metrics (request count, latency histogram)
- Error rate tracking
- Slow request detection (>2s warning)
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.core.logger import set_correlation_id

logger = logging.getLogger(__name__)

# Slow request threshold
_SLOW_REQUEST_THRESHOLD_S = 2.0

# Lazy prometheus import
try:
    from prometheus_client import Counter, Histogram
    _REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    _REQUEST_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


def _normalise_path(path: str) -> str:
    """Replace UUIDs and numeric IDs with placeholders to avoid cardinality explosion."""
    import re
    path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path)
    path = re.sub(r'/\d+', '/{id}', path)
    return path


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request logging, correlation IDs, and Prometheus metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Correlation ID
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_correlation_id(cid)

        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            logger.error("Unhandled exception in middleware: %s", exc, exc_info=True)
            raise
        finally:
            elapsed = time.perf_counter() - start
            normalised = _normalise_path(request.url.path)

            if _HAS_PROMETHEUS:
                _REQUEST_COUNT.labels(
                    method=request.method,
                    path=normalised,
                    status=str(status_code),
                ).inc()
                _REQUEST_LATENCY.labels(
                    method=request.method,
                    path=normalised,
                ).observe(elapsed)

            # Structured access log
            log_fn = logger.warning if elapsed > _SLOW_REQUEST_THRESHOLD_S else logger.info
            log_fn(
                "%s %s %d %.3fs [%s]",
                request.method,
                request.url.path,
                status_code,
                elapsed,
                cid,
            )

            if elapsed > _SLOW_REQUEST_THRESHOLD_S:
                logger.warning(
                    "SLOW REQUEST: %s %s took %.3fs (threshold %.1fs)",
                    request.method, request.url.path, elapsed, _SLOW_REQUEST_THRESHOLD_S,
                )

        response.headers["X-Request-ID"] = cid
        return response
