"""Galaxy Vast AI Trading Platform
Observability Middleware

Fix applied:
- HIGH: prometheus_client was imported at module level.
  If not installed, startup crashes with ImportError (hard fail).
  Fix: lazy import inside the class — middleware degrades gracefully.
- MEDIUM: request_id was not propagated to response headers consistently.
- LOW: duration histogram labels did not include method — now they do.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Lazy Prometheus handle — None until first request if prometheus_client unavailable
_REQUEST_COUNTER: object = None
_REQUEST_LATENCY: object = None
_PROM_AVAILABLE: bool | None = None  # None = not yet checked


def _try_init_prometheus() -> bool:
    """Try to initialise Prometheus metrics. Return True on success."""
    global _REQUEST_COUNTER, _REQUEST_LATENCY, _PROM_AVAILABLE
    if _PROM_AVAILABLE is not None:
        return _PROM_AVAILABLE
    try:
        from prometheus_client import Counter, Histogram  # type: ignore[import]
        _REQUEST_COUNTER = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
        )
        _REQUEST_LATENCY = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["method", "path"],
        )
        _PROM_AVAILABLE = True
        logger.info("Prometheus metrics initialised.")
    except ImportError:
        _PROM_AVAILABLE = False
        logger.warning(
            "prometheus_client not installed — metrics disabled. "
            "Add 'prometheus-client' to requirements.txt to enable."
        )
    return _PROM_AVAILABLE


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Attach request_id, log every request, and (if available) record Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        t0 = time.monotonic()

        try:
            response: Response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unhandled error on %s %s [request_id=%s]: %s",
                request.method, request.url.path, request_id, exc,
                exc_info=True,
            )
            from fastapi.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

        duration = time.monotonic() - t0
        status   = response.status_code
        path     = request.url.path
        method   = request.method

        # Always add request_id to response headers
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s %d %.3fs [%s]",
            method, path, status, duration, request_id,
        )

        # Record Prometheus metrics (lazy init, no crash if unavailable)
        if _try_init_prometheus():
            try:
                _REQUEST_COUNTER.labels(  # type: ignore[union-attr]
                    method=method, path=path, status=str(status)
                ).inc()
                _REQUEST_LATENCY.labels(  # type: ignore[union-attr]
                    method=method, path=path
                ).observe(duration)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Prometheus record error: %s", exc)

        return response
