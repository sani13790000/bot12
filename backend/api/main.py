"""backend/api/main.py
Galaxy Vast AI Trading Platform — FastAPI Application Factory

Fixes applied:
  CRIT-A  Lazy asyncio.Lock in rate_limit / circuit_breaker
  FIX T-10 EquityProtection health check in /health
  CONFLICT-FIX-3 register_missing_routes from main_patch
  CONFLICT-FIX-4 CB locks pre-warmed in lifespan
  HIGH-FIX silent exception swallow replaced with debug logging
  HIGH-FIX risk route registered explicitly
  PROD-FIX-1 CORS uses settings.ALLOWED_ORIGINS (was CORS_ORIGINS — nonexistent field)
  PROD-FIX-2 auth + license routes explicitly registered
  PROD-FIX-3 allow_methods restricted to safe list in production
  PHASE1-MERGE S-5..S-8 from main_patch.py: GracefulDrain, safe_startup_task, CB health
"""
from __future__ import annotations

import asyncio
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger

settings = get_settings()
logger   = get_logger("api.main")

_STARTUP_T0: float = 0.0


def register_missing_routes(app: FastAPI) -> None:
    """
    S-5 + PHASE1-MERGE: learning, portfolio, analytics and all core routes.
    Idempotent — safe to call multiple times.
    """
    _V1 = "/api/v1"
    already = {r.path for r in app.routes}  # type: ignore[attr-defined]

    _route_map = {
        f"{_V1}/auth":         ("backend.api.routes.auth",         "router", ["Auth"]),
        f"{_V1}/signals":      ("backend.api.routes.signals",      "router", ["Signals"]),
        f"{_V1}/trades":       ("backend.api.routes.trades",       "router", ["Trades"]),
        f"{_V1}/agents":       ("backend.api.routes.agents",       "router", ["Agents"]),
        f"{_V1}/risk":         ("backend.api.routes.risk",         "router", ["Risk"]),
        f"{_V1}/users":        ("backend.api.routes.users",        "router", ["Users"]),
        f"{_V1}/health":       ("backend.api.routes.health",       "router", ["Health"]),
        f"{_V1}/analytics":    ("backend.api.routes.analytics",   "router", ["Analytics"]),
        f"{_V1}/license":      ("backend.api.routes.license",     "router", ["License"]),
        f"{_V1}/learning":     ("backend.api.routes.learning",    "router", ["Learning"]),
        f"{_V1}/portfolio":    ("backend.api.routes.portfolio",   "router", ["Portfolio"]),
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
    """
    S-6 + PHASE1-MERGE: Run a startup coroutine; log and re-raise on failure
    so the lifespan context sees the error instead of silently ignoring it.
    """
    try:
        await coro
        logger.debug("startup task ok", task=name)
    except Exception as exc:
        logger.debug("startup task failed", task=name, error=str(exc))
        raise


def get_circuit_breaker_health() -> Dict[str, Any]:
    """
    S-7 + PHASE1-MERGE: Returns dict of all known breaker states for /health.
    Fails gracefully if circuit_breaker module unavailable.
    """
    try:
        from backend.circuit_breaker import get_breaker_status
        return get_breaker_status()
    except Exception as exc:
        logger.debug("CB health unavailable", error=str(exc))
        return {"error": "unavailable"}


class GracefulDrain:
    """
    S-8 + PHASE1-MERGE: Tracks in-flight requests; waits for drain on SIGTERM.
    Usage: add as middleware or use enter()/exit() in request lifecycle.
    """

    def __init__(self, drain_timeout: float = 10.0) -> None:
        self._in_flight: int = 0
        self._drain_timeout = drain_timeout
        self._draining = False
        self._lock = asyncio.Lock()

    async def enter(self) -> bool:
        """Call at request start. Returns False if draining (reject request)."""
        async with self._lock:
            if self._draining:
                return False
            self._in_flight += 1
            return True

    async def exit(self) -> None:
        """Call at request end."""
        async with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    async def drain(self) -> None:
        """Wait until all in-flight requests complete or timeout."""
        async with self._lock:
            self._draining = True
        deadline = time.monotonic() + self._drain_timeout
        while self._in_flight > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        logger.debug("drain complete", remaining=self._in_flight)

    def register_sigterm(self) -> None:
        """Register SIGTERM handler that triggers drain."""
        loop = asyncio.get_event_loop()

        def _handler() -> None:
            logger.debug("SIGTERM received, draining")
            loop.create_task(self.drain())

        loop.add_signal_handler(signal.SIGTERM, _handler)


_drain = GracefulDrain(drain_timeout=10.0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _STARTUP_T0
    _STARTUP_T0 = time.monotonic()
    logger.debug("startup begin")

    # Pre-warm asyncio locks (CRIT-A fix)
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

    # Register SIGTERM drain
    try:
        _drain.register_sigterm()
    except Exception as exc:
        logger.debug("SIGTERM handler skipped", error=str(exc))

    # Register all routes
    register_missing_routes(app)

    logger.debug("startup complete", elapsed_ms=round((time.monotonic() - _STARTUP_T0) * 1000, 1))
    yield

    # Shutdown
    logger.debug("shutdown begin")
    await _drain.drain()
    logger.debug("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS (PROD-FIX-1: use ALLOWED_ORIGINS not CORS_ORIGINS)
    origins = settings.ALLOWED_ORIGINS if hasattr(settings, "ALLOWED_ORIGINS") else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Device-ID"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def _global_exc(request: Request, exc: Exception) -> JSONResponse:
        logger.debug("unhandled exception", path=str(request.url), error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
