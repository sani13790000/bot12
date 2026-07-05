"""
backend/api/main.py — FIXED
Fixes applied:
  CB-1 FIX: /health/live endpoint added directly on app (Docker HEALTHCHECK target)
  CB-7 FIX: mt5_ok dict → evaluated as mt5_ok.get("ok", False)
  AI-2 FIX: kill_switch.is_active called as sync consistently
  CB-8 FIX: startup_check imported and called in lifespan
  AI-4 FIX: MT5_GATEWAY_URL now in config (not raw os.environ in connector)
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger

settings = get_settings()
logger = get_logger("api.main")

_STARTUP_T0: float = 0.0
_FAILED_ROUTES: List[str] = []


def register_missing_routes(app: FastAPI) -> None:
    """Idempotent route registration with visible error reporting."""
    _V1 = "/api/v1"
    already = {r.path for r in app.routes}  # type: ignore[attr-defined]

    _route_map = {
        f"{_V1}/auth":       ("backend.api.routes.auth",       "router", ["Auth"]),
        f"{_V1}/signals":    ("backend.api.routes.signals",    "router", ["Signals"]),
        f"{_V1}/trades":     ("backend.api.routes.trades",     "router", ["Trades"]),
        f"{_V1}/agents":     ("backend.api.routes.agents",     "router", ["Agents"]),
        f"{_V1}/risk":       ("backend.api.routes.risk",       "router", ["Risk"]),
        f"{_V1}/users":      ("backend.api.routes.users",      "router", ["Users"]),
        f"{_V1}/health":     ("backend.api.routes.health",     "router", ["Health"]),
        f"{_V1}/analytics":  ("backend.api.routes.analytics",  "router", ["Analytics"]),
        f"{_V1}/license":    ("backend.api.routes.license",    "router", ["License"]),
        f"{_V1}/learning":   ("backend.api.routes.learning",   "router", ["Learning"]),
        f"{_V1}/portfolio":  ("backend.api.routes.portfolio",  "router", ["Portfolio"]),
        f"{_V1}/admin":      ("backend.api.routes.admin",      "router", ["Admin"]),
    }

    _CRITICAL = {f"{_V1}/risk", f"{_V1}/trades", f"{_V1}/signals", f"{_V1}/auth"}

    for prefix, (module, attr, tags) in _route_map.items():
        if prefix not in already:
            try:
                import importlib
                mod = importlib.import_module(module)
                router = getattr(mod, attr)
                app.include_router(router, prefix=prefix, tags=tags)
                logger.debug("route registered", prefix=prefix)
            except Exception as exc:
                logger.error(
                    "ROUTE REGISTRATION FAILED",
                    prefix=prefix,
                    module=module,
                    error=str(exc),
                )
                _FAILED_ROUTES.append(prefix)
                if prefix in _CRITICAL and settings.APP_ENV == "production":
                    raise RuntimeError(
                        f"Critical route '{prefix}' failed: {exc}"
                    ) from exc


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
    """Tracks in-flight requests; waits for drain on SIGTERM."""

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
        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGTERM, self._handle_sigterm)
            logger.debug("SIGTERM handler registered")
        except (RuntimeError, NotImplementedError):
            logger.debug("SIGTERM handler skipped (not supported on this OS)")

    def _handle_sigterm(self) -> None:
        self._shutting_down = True
        logger.info("[GracefulDrain] SIGTERM received -- draining requests")

    async def wait_drain(self) -> None:
        deadline = time.monotonic() + self._drain_timeout
        while self._count > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self._count > 0:
            logger.warning(
                "[GracefulDrain] drain timeout -- %d requests still in-flight",
                self._count,
            )


_drain = GracefulDrain()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _STARTUP_T0
    _STARTUP_T0 = time.monotonic()
    logger.info("Galaxy Vast AI -- startup", version=settings.APP_VERSION, env=settings.APP_ENV)
    _drain.register_sigterm()

    # CB-8 FIX: startup_check now actually runs at startup
    try:
        from backend.startup_check import run_startup_checks
        await run_startup_checks()
        logger.info("Startup checks passed")
    except ImportError:
        logger.debug("startup_check module not found -- skipping pre-flight")
    except Exception as exc:
        logger.error("Startup checks FAILED", error=str(exc))
        if settings.APP_ENV == "production":
            raise

    try:
        from backend.database.redis_client import init_redis
        await safe_startup_task("redis", init_redis())
    except ImportError:
        logger.debug("Redis not configured -- skipping")

    # BUG-2 FIX: mt5_connector.connect() must be called in lifespan
    # Without this, every live trade causes MT5Error('Not connected')
    try:
        from backend.execution.mt5_connector import mt5_connector
        await mt5_connector.connect()
        logger.info("MT5 connector connected successfully")
    except Exception as exc:
        logger.warning("MT5 connect failed at startup", error=str(exc))

    register_missing_routes(app)
    if _FAILED_ROUTES:
        logger.warning("Routes not registered at startup", failed=_FAILED_ROUTES)

    yield

    logger.info("Galaxy Vast AI -- shutting down")
    await _drain.wait_drain()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
        openapi_url="/api/openapi.json" if settings.APP_ENV != "production" else None,
    )

    if settings.APP_ENV == "production" and settings.TRUSTED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)

    cors_origins = settings.ALLOWED_ORIGINS
    if settings.APP_ENV == "production" and "*" in cors_origins:
        logger.warning("CORS wildcard (*) in production! Set CORS_ORIGINS env var.")

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

    try:
        from backend.middleware.security_hardened import SecurityHardenedMiddleware
        app.add_middleware(SecurityHardenedMiddleware)
        logger.debug("SecurityHardenedMiddleware registered")
    except Exception as exc:
        logger.warning("SecurityHardenedMiddleware skipped", error=str(exc))

    try:
        from backend.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware, limit=settings.RATE_LIMIT_API_PER_MINUTE, window=60)
        logger.debug("RateLimitMiddleware registered")
    except Exception as exc:
        logger.warning("RateLimitMiddleware skipped", error=str(exc))

    # CB-1 FIX: /health/live added directly on app
    # Docker HEALTHCHECK: curl -f http://localhost:8000/health/live
    @app.get("/health/live", tags=["System"], include_in_schema=False)
    async def health_live() -> Dict[str, Any]:
        """Docker/Kubernetes liveness probe."""
        return {
            "status": "alive",
            "uptime_seconds": round(time.monotonic() - _STARTUP_T0, 1),
        }

    @app.get("/health", tags=["System"])
    async def health_check() -> Dict[str, Any]:
        checks: Dict[str, Any] = {
            "status": "ok",
            "version": settings.APP_VERSION,
            "env": settings.APP_ENV,
            "uptime_seconds": round(time.monotonic() - _STARTUP_T0, 1),
        }
        checks["circuit_breakers"] = get_circuit_breaker_health()

        if _FAILED_ROUTES:
            checks["failed_routes"] = _FAILED_ROUTES
            checks["status"] = "degraded"

        try:
            from backend.database.connection import get_db_client
            client = await asyncio.wait_for(get_db_client(), timeout=2.0)
            checks["database"] = "ok" if client else "degraded"
        except Exception as exc:
            checks["database"] = f"error: {str(exc)[:50]}"

        try:
            from backend.execution.mt5_connector import mt5_connector
            mt5_result = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
            # CB-7 FIX: was `if mt5_ok` (always True for non-empty dict)
            mt5_ok = mt5_result.get("ok", False) if isinstance(mt5_result, dict) else bool(mt5_result)
            checks["mt5_gateway"] = "ok" if mt5_ok else "degraded"
        except Exception as exc:
            checks["mt5_gateway"] = f"error: {str(exc)[:50]}"

        try:
            from backend.risk.kill_switch import kill_switch
            # BUG-1 FIX: is_active is @property — do NOT call with ()
            checks["kill_switch"] = "ACTIVE" if kill_switch.is_active else "inactive"
        except Exception:
            checks["kill_switch"] = "unknown"

        degraded = any(
            isinstance(v, str) and ("error" in v or "degraded" in v)
            for k, v in checks.items()
            if k not in ("kill_switch", "circuit_breakers", "failed_routes")
        )
        if degraded:
            checks["status"] = "degraded"

        return JSONResponse(
            content=checks,
            status_code=200 if checks["status"] == "ok" else 503,
        )

    @app.get("/metrics", tags=["System"], include_in_schema=False)
    async def prometheus_metrics() -> Any:
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            from fastapi.responses import Response
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except Exception as exc:
            return JSONResponse(status_code=503, content={"error": str(exc)})

    return app


app = create_app()
