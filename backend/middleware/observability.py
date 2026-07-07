"""Observability middleware. Phase L fixes L-9/L-10/L-11/L-12."""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.observability.structured_logger import set_request_context

logger = logging.getLogger(__name__)
_SLOW_REQUEST_THRESHOLD_S = 2.0

_REQUEST_COUNT = None
_REQUEST_LATENCY = None
_HAS_PROMETHEUS = False

try:
    from prometheus_client import REGISTRY, Counter, Histogram

    def _get_or_create(cls, name, desc, labels, **kwargs):
        try:
            return cls(name, desc, labels, **kwargs)
        except ValueError:
            return REGISTRY._names_to_collectors.get(name)

    _REQUEST_COUNT = _get_or_create(
        Counter,
        "gv_mw_http_requests_total",
        "Total HTTP requests (middleware)",
        ["method", "path", "status"],
    )
    _REQUEST_LATENCY = _get_or_create(
        Histogram,
        "gv_mw_http_request_duration_seconds",
        "HTTP request latency (middleware)",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    _HAS_PROMETHEUS = True
except ImportError:
    pass

_UUID_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"/\d+")


def _normalise_path(path: str) -> str:
    path = _UUID_RE.sub("/{uuid}", path)
    path = _ID_RE.sub("/{id}", path)
    return path


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_context(request_id=cid)

        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = cid
        except Exception as exc:
            logger.error("Unhandled exception in middleware: %s", exc, exc_info=True)
            raise
        finally:
            elapsed = time.perf_counter() - start
            normalised = _normalise_path(request.url.path)
            if _HAS_PROMETHEUS and _REQUEST_COUNT and _REQUEST_LATENCY:
                _REQUEST_COUNT.labels(
                    method=request.method, path=normalised, status=str(status_code)
                ).inc()
                _REQUEST_LATENCY.labels(method=request.method, path=normalised).observe(elapsed)
            log_fn = logger.warning if elapsed > _SLOW_REQUEST_THRESHOLD_S else logger.info
            log_fn(
                "%s %s %d %.3fs cid=%s", request.method, request.url.path, status_code, elapsed, cid
            )
        return response
