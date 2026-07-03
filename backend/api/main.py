"""backend/api/main.py — Phase I Production Hardening
Fixes:
  I-1: CORS from ALLOWED_ORIGINS (alias in config) — no more ["*"] fallback
  I-2: SecurityHardenedMiddleware added
  I-3: RateLimitMiddleware added as ASGI middleware
  I-4: TrustedHostMiddleware with TRUSTED_HOSTS from env
  I-5: init_redis called in lifespan
  I-6: /health endpoint with CB + DB + MT5
  I-7: GracefulDrain with docker-safe SIGTERM
  I-8: /metrics Prometheus endpoint
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger

settings = get_settings()
logger = get_logger("api.main")

_STARTUP_T0: float = 0.0


def register_missing_routes(app: FastAPI) -> None:
    """Idempotent route registration."""
    _V1 = "/api/v1"
    already = {r.path for r in app.routes}  # type: ignore[attr-defined]

    _route_map = {
        f"{_V1}/auth":      ("backend.api.routes.auth",      "router", ["Auth"]),
        f"{_V1}/signals":   ("backend.api.routes.signals",   "router", ["Signals"]),
        f"{_V1}/trades":    ("backend.api.routes.trades",    "router", ["Trades"]),
        f"{_V1}/agents":    ("backend.api.routes.agents",    "router", ["Agents"]),
        f"{_V1}/risk":      ("backend.api.routes.risk",      "router", ["Risk"]),
        f"{_V1}/users":     ("backend.api.routes.users",     "router", ["Users"]),
        f"{_V1}/health":    ("backend.api.routes.health",    "router", ["Health"]),
        f"{_V1}/analytics": ("backend.api.routes.analytics", "router", ["Analytics"]),
        f"{_V1}/license":   ("backend.api.routes.license",   "router", ["License"]),
        f"{_V1}/learning":  ("backend.api.routes.learning",  "router", ["Learning"]),
        f"{_V1}/portfolio": ("backend.api.routes.portfolio", "router", ["Portfolio"]),
        f"{_V1}/admin":     ("backend.api.routes.admin",     "router", ["Admin"]),
    }

    for prefix, (module, attr, tags) in _route_map.items():
        if prefix not in already:
            try:
                import importlib
                mod = importlib.import_module(module)
                router = getattr(mod, attr)
                app.include_router(router, prefix=prefix, tags=tags)
                logger.debug("route registered", prefix=prefix)
            except Exception as exc:
                logger.debug("route not available", prefix=prefix, error=str(exc))


async def safe_startup_task(name: str, coro: Any) -> None:
    try:
        await coro
        logger.debug("startup task ok", task=name)
    except Exception as exc:
        logger.warning("startup task failed", task=name, error=str(exc))
        raise


def get_circuit_breaker_health() -> Dict[str, Any]:
    try:
        from backend.circuit_breaker import get_breaker_status
        return get_breaker_status()
    except Exception as exc:
        logger.debug("CB health unavailable", error=str(exc))
        return {"status": "unavailable"}


class GracefulDrain:
    """Tracks in-flight requests; waits for drain on SIGTERM (docker-safe)."""

    def __init__(self, drain_timeout: float = 10.0) -> None:
        self._count = 0
        self._lock = asyncio.Lock()
        self._drain_timeout = drain_timeout
        self._shutting_down = False

    async def enter(self) -> None:
        async with self._lock:
            self._count += 1

    async def exit(self) -> None:
        async with self._lock:
            self._count = max(0, self._count - 1)

    def register_sigterm(self) -> None:
        """I-7: docker-safe SIGTERM via event loop."""
        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGTERM, self._handle_sigterm)
            logger.debug("SIGTERM handler registered")
        except (RuntimeError, NotImplementedError):
            logger.debug("SIGTERM handler skipped (not supported on this OS)")

    def _handle_sigterm(self) -> None:
        self._shutting_down = True
        logger.info("SIGTERM received — draining requests")

    async def drain(self) -> None:
        deadline = time.monotonic() + self._drain_timeout
        while time.monotonic() < deadline:
            async with self._lock:
                if self._count == 0:
                    break
            await asyncio.sleep(0.1)
        async with self._lock:
            if self._count > 0:
                logger.warning("drain timeout", remaining=self._count)


_drain = GracefulDrain(drain_timeout=10.0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _STARTUP_T0
    _STARTUP_T0 = time.monotonic()
    logger.info("startup begin")

    # I-5: init Redis for distributed rate limiting
    try:
        from backend.middleware.rate_limit import init_redis
        if settings.REDIS_URL:
            await safe_startup_task("redis", init_redis(settings.REDIS_URL))
        else:
            logger.debug("REDIS_URL not set — using in-memory rate limiting")
    except Exception as exc:
        logger.debug("Redis init skipped", error=str(exc))

    # Pre-warm asyncio locks
    try:
        from backend.middleware.rate_limit import get_rate_limiter
        await get_rate_limiter()
    except Exception as exc:
        logger.debug("rate limiter pre-warm skipped", error=str(exc))

    try:
        from backend.circuit_breaker import get_circuit_breaker
        await get_circuit_breaker("broker")
    except Exception as exc:
        logger.debug("circuit breaker pre-warm skipped", error=str(exc))

    # I-7: docker-safe SIGTERM
    try:
        _drain.register_sigterm()
    except Exception as exc:
        logger.debug("SIGTERM handler skipped", error=str(exc))

    register_missing_routes(app)

    elapsed = round((time.monotonic() - _STARTUP_T0) * 1000, 1)
    logger.info("startup complete", elapsed_ms=elapsed)
    yield

    logger.info("shutdown begin")
    await _drain.drain()

    try:
        from backend.middleware.rate_limit import close_redis
        await close_redis()
    except Exception:
        pass

    logger.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
        openapi_url="/api/openapi.json" if settings.APP_ENV != "production" else None,
    )

    # I-4: TrustedHostMiddleware
    if settings.APP_ENV == "production" and settings.TRUSTED_HOSTS:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.TRUSTED_HOSTS,
        )

    # I-1: CORS — uses ALLOWED_ORIGINS property (no ["*"] fallback)
    cors_origins = settings.ALLOWED_ORIGINS
    if settings.APP_ENV == "production" and "*" in cors_origins:
        logger.warning("CORS wildcard (*) detected in production! Set CORS_ORIGINS env var.")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-Request-ID",
            "X-Device-ID", "X-License-Key", "Accept", "Accept-Language",
        ],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )

    # I-2: Security Headers + WAF
    try:
        from backend.middleware.security_hardened import SecurityHardenedMiddleware
        app.add_middleware(SecurityHardenedMiddleware)
        logger.debug("SecurityHardenedMiddleware registered")
    except Exception as exc:
        logger.warning("SecurityHardenedMiddleware skipped", error=str(exc))

    # I-3: Rate Limiting
    try:
        from backend.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(
            RateLimitMiddleware,
            limit=settings.RATE_LIMIT_API_PER_MINUTE,
            window=60,
        )
        logger.debug("RateLimitMiddleware registered")
    except Exception as exc:
        logger.warning("RateLimitMiddleware skipped", error=str(exc))

    # I-6: /health endpoint
    @app.get("/health", tags=["System"])
    async def health_check() -> Dict[str, Any]:
        checks: Dict[str, Any] = {
            "status": "ok",
            "version": settings.APP_VERSION,
            "env": settings.APP_ENV,
            "uptime_seconds": round(time.monotonic() - _STARTUP_T0, 1),
        }
        checks["circuit_breakers"] = get_circuit_breaker_health()

        try:
            from backend.database.connection import db
            ping_ok = await asyncio.wait_for(db.ping(), timeout=2.0)
            checks["database"] = "ok" if ping_ok else "degraded"
        except Exception as exc:
            checks["database"] = f"error: {str(exc)[:50]}"

        try:
            from backend.execution.mt5_connector import mt5_connector
            mt5_ok = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
            checks["mt5_gateway"] = "ok" if mt5_ok else "degraded"
        except Exception as exc:
            checks["mt5_gateway"] = f"error: {str(exc)[:50]}"

        try:
            from backend.risk.kill_switch import kill_switch
            checks["kill_switch"] = "ACTIVE" if kill_switch.is_active() else "inactive"
        except Exception:
            checks["kill_switch"] = "unknown"

        degraded = any(
            isinstance(v, str) and ("error" in v or "degraded" in v)
            for k, v in checks.items()
            if k not in ("kill_switch", "circuit_breakers")
        )
        if degraded:
            checks["status"] = "degraded"

        return JSONResponse(content=checks, status_code=200 if checks["status"] == "ok" else 503)

    # I-8: /metrics
    @app.get("/metrics", tags=["System"], include_in_schema=False)
    async def prometheus_metrics() -> Any:
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            from fastapi.responses import Response as FastAPIResponse
            return FastAPIResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except ImportError:
            return JSONResponse(status_code=503, content={"error": "prometheus_client not installed"})

    @app.exception_handler(Exception)
    async def _global_exc(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled exception",
            path=str(request.url.path),
            method=request.method,
            error=str(exc)[:200],
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
