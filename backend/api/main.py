"""backend/api/main.py -- Round 6 Restored + All Fixes Applied
BUG-R6-1: Restored from placeholder
BUG-R5-1: asyncio.get_running_loop() in GracefulDrain (Python 3.12 safe)
BUG-R5-4: signal_processor.register_agents() called in lifespan
BUG-R4-4: _stale_order_cleaner background task
ARCH-R4-5: _position_reconciler background task (safe with hasattr guard)
ARCH-R5-6/R6: CORS uses settings.ALLOWED_ORIGINS
BUG-R2-1: /health/live endpoint for Docker healthcheck
BUG-R3-2: mt5_connector.connect() called in lifespan
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
        self._lock: Any = None  # BUG-R6-6 FIX: lazy init, not in __init__
        self._drain_timeout = drain_timeout
        self._shutting_down = False

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def enter(self) -> None:
        async with self._get_lock():
            self._count += 1

    async def exit(self) -> None:
        async with self._get_lock():
            self._count = max(0, self._count - 1)

    def register_sigterm(self) -> None:
        try:
            # BUG-R5-1 FIX: get_running_loop() — not deprecated get_event_loop()
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, self._handle_sigterm)
            logger.debug("SIGTERM handler registered")
        except (RuntimeError, NotImplementedError, OSError):
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

    try:
        from backend.startup_check import run_startup_checks
        await run_startup_checks()
    except Exception as exc:
        logger.warning("startup checks failed", error=str(exc))

    try:
        from backend.database.redis_client import init_redis
        await safe_startup_task("redis", init_redis())
    except ImportError:
        logger.debug("Redis not configured -- skipping")

    try:
        from backend.execution.mt5_connector import mt5_connector
        await safe_startup_task("mt5", mt5_connector.connect())
    except ImportError:
        logger.debug("MT5 not configured -- skipping")

    # BUG-R5-4 FIX: register agents for VotingEngine quorum
    try:
        from backend.services.signal_processor import signal_processor
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.ml_agent import MLAgent
        from backend.agents.news_agent import NewsAgent
        signal_processor.register_agents([SMCAgent(), MLAgent(), NewsAgent()])
        logger.info("Agents registered for VotingEngine")
    except Exception as exc:
        logger.warning("Agent registration failed", error=str(exc))

    async def _stale_order_cleaner() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                from backend.execution.order_state_machine import order_state_machine
                order_state_machine.expire_stale_tickets()
            except Exception as exc:
                logger.debug("stale order cleaner skipped", error=str(exc))

    async def _position_reconciler() -> None:
        interval = settings.RECONCILE_INTERVAL_SECONDS
        while True:
            await asyncio.sleep(interval)
            try:
                from backend.execution.mt5_connector import mt5_connector
                from backend.execution.order_state_machine import order_state_machine
                # ARCH-R5-8 FIX: safe hasattr guard — get_positions may not exist
                if hasattr(mt5_connector, "get_positions"):
                    live = await mt5_connector.get_positions()
                    live_tickets = {p.get("ticket") for p in live}
                    for ticket in order_state_machine.active_tickets():
                        if ticket not in live_tickets:
                            logger.warning("reconcile: ticket %s not in MT5", ticket)
            except Exception as exc:
                logger.debug("reconciler skipped", error=str(exc))

    asyncio.create_task(_stale_order_cleaner())
    asyncio.create_task(_position_reconciler())

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

    # ARCH-R5-6 FIX: ALLOWED_ORIGINS not getattr fallback to ["*"]
    cors_origins = settings.ALLOWED_ORIGINS
    if settings.APP_ENV == "production" and "*" in cors_origins:
        logger.warning("CORS wildcard (*) in production! Set ALLOWED_ORIGINS env var.")

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
            mt5_ok = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
            is_okay = mt5_ok.get("ok", False) if isinstance(mt5_ok, dict) else bool(mt5_ok)
            checks["mt5_gateway"] = "ok" if is_okay else "degraded"
        except Exception as exc:
            checks["mt5_gateway"] = f"error: {str(exc)[:50]}"

        try:
            from backend.risk.kill_switch import kill_switch
            # BUG-R6-1 FIX: is_active is @property — no ()
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

    @app.get("/health/live", tags=["System"])
    async def health_live() -> Dict[str, Any]:
        """BUG-R2-1 FIX: Docker HEALTHCHECK target."""
        return JSONResponse(content={"status": "ok"}, status_code=200)

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
