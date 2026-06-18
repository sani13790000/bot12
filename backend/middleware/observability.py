"""
faz 9 - Observability Middleware
Auto request_id, trace_id, duration tracking, metrics per endpoint
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.observability.metrics import metrics_registry
from backend.observability.structured_logger import set_request_context, get_logger

logger = get_logger("middleware.observability")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Injects request_id, trace_id, measures duration, records metrics"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())[:8]
        user_id = ""

        # Set context for this request
        set_request_context(
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
        )

        # Track active requests
        metrics_registry.http_active_requests.inc()
        start = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            metrics_registry.http_errors_total.inc()
            logger.error(
                f"Unhandled error: {exc}",
                path=request.url.path,
                method=request.method,
            )
            raise
        finally:
            duration = time.time() - start
            metrics_registry.http_active_requests.dec()
            metrics_registry.http_requests_total.inc()
            metrics_registry.http_request_duration.observe(duration)

            if status_code >= 400:
                metrics_registry.http_errors_total.inc()

            # Log slow requests
            if duration > 1.0:
                logger.warning(
                    f"Slow request: {request.method} {request.url.path} took {duration*1000:.0f}ms",
                    duration_ms=duration * 1000,
                    status_code=status_code,
                    request_id=request_id,
                )
            else:
                logger.info(
                    f"{request.method} {request.url.path} {status_code} {duration*1000:.1f}ms",
                    status_code=status_code,
                    duration_ms=round(duration * 1000, 1),
                    request_id=request_id,
                )

        # Add tracing headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response
