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
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger

settings = get_settings()
logger   = get_logger("api.main")

_STARTUP_T0: float = 0.0


# ── Equity Protection helper ─────────────────────────────────────────────────────

async def _initialize_equity_protection() -> None:
    try:
        from ..risk.equity_protection import EquityProtectionEngine, EquityProtectionConfig
        ep = EquityProtectionEngine(EquityProtectionConfig())
        logger.info("EquityProtection initialised", config=str(ep._config))
    except Exception as exc:
        logger.warning("EquityProtection init skipped", error=str(exc))


async def _run_equity_gate() -> bool:
    try:
        from ..risk.equity_protection import EquityProtectionEngine, EquityProtectionConfig
        ep  = EquityProtectionEngine(EquityProtectionConfig())
        res = ep.check()
        return res.can_trade
    except Exception as exc:
        logger.debug("equity gate check failed", error=str(exc))
        return True


# ── Lifespan ─────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _STARTUP_T0
    _STARTUP_T0 = time.monotonic()
    logger.info("Galaxy Vast AI startup", env=settings.ENVIRONMENT)

    # Rate limit cleanup
    try:
        from ..middleware.rate_limit import start_cleanup_task
        await start_cleanup_task()
    except Exception as exc:
        logger.debug("rate_limit cleanup task skipped", error=str(exc))

    # Equity protection
    await _initialize_equity_protection()

    # CONFLICT-FIX-3: Register missing routes (learning / portfolio / security-ai)
    try:
        from .main_patch import register_missing_routes
        register_missing_routes(app)
        logger.info("Missing routes registered via main_patch")
    except Exception as exc:
        logger.debug("register_missing_routes skipped", error=str(exc))

    # CONFLICT-FIX-4: Pre-warm circuit breaker lazy locks
    try:
        from ..circuit_breaker import _get_halt_lock, _get_registry_lock
        _get_halt_lock()
        _get_registry_lock()
        logger.info("CircuitBreaker locks pre-warmed")
    except Exception as exc:
        logger.debug("CB pre-warm skipped", error=str(exc))

    logger.info("Startup complete", elapsed_s=round(time.monotonic() - _STARTUP_T0, 2))

    yield

    # Shutdown
    logger.info("Galaxy Vast AI shutting down")
    try:
        from ..middleware.rate_limit import close_redis
        await close_redis()
    except Exception as exc:
        logger.debug("Redis close skipped", error=str(exc))


# ── Application factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version="2.0.0",
        description="Enterprise AI-powered Forex trading platform with 7-gate risk management",
        lifespan=lifespan,
        docs_url  ="/docs"  if settings.ENVIRONMENT != "production" else None,
        redoc_url ="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # PROD-FIX-1: was settings.CORS_ORIGINS (nonexistent) → always fell back to localhost only
    allowed_origins = settings.ALLOWED_ORIGINS or ["http://localhost:3000"]

    # PROD-FIX-3: restrict methods in production
    allowed_methods = (
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        if settings.ENVIRONMENT == "production"
        else ["*"]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    )

    # ── Rate Limit ─────────────────────────────────────────────────────────────
    try:
        from ..middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
    except Exception as exc:
        logger.debug("RateLimitMiddleware skipped", error=str(exc))

    # ── Routes ───────────────────────────────────────────────────────────────────
    _prefix = settings.API_PREFIX

    from .health import router as health_router
    app.include_router(health_router, tags=["Health"])

    # PROD-FIX-2: auth + license routes explicitly registered (were missing before)
    _route_map = [
        ("routes.auth",     f"{_prefix}/auth",     ["Authentication"]),
        ("routes.license",  f"{_prefix}/license",  ["License"]),
        ("routes.signals",  f"{_prefix}/signals",  ["Signals"]),
        ("routes.trades",   f"{_prefix}/trades",   ["Trades"]),
        ("routes.users",    f"{_prefix}/users",    ["Users"]),
        ("routes.risk",     f"{_prefix}/risk",     ["Risk"]),
        ("routes.agents",   f"{_prefix}/agents",   ["Agents"]),
        ("routes.analytics",f"{_prefix}/analytics",["Analytics"]),
        ("routes.backtest", f"{_prefix}/backtest", ["Backtest"]),
        ("routes.ai_prediction", f"{_prefix}/ai-prediction", ["AI Prediction"]),
        ("routes.intelligence",  f"{_prefix}/intelligence",  ["Intelligence"]),
        ("routes.dashboard",     f"{_prefix}/dashboard",     ["Dashboard"]),
    ]
    for module, prefix, tags in _route_map:
        try:
            import importlib
            mod = importlib.import_module(f".{module}", package=__package__)
            app.include_router(mod.router, prefix=prefix, tags=tags)
            logger.debug("Route registered", prefix=prefix)
        except Exception as exc:
            logger.debug("Route skipped", module=module, error=str(exc))

    # ── Global exception handler ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
        )

    return app


# ── Module-level singleton ──────────────────────────────────────────────────────────

app = create_app()


# ── Liveness probe (keep for backward compat) ──────────────────────────────────

@app.get("/ping", include_in_schema=False)
async def ping() -> dict:
    return {"status": "ok", "uptime_s": round(time.monotonic() - _STARTUP_T0, 1)}
