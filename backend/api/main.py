"""Galaxy Vast AI Trading Platform - FastAPI Application
Production-grade: structured logging, health checks, graceful shutdown,
retry policies, monitoring hooks, error tracking, validation layers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, List

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Core ─────────────────────────────────────────────────────────────────────
from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

# ── Middleware (hard import — no silent fail) ─────────────────────────────────
from backend.middleware.security import SecurityMiddleware
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.middleware.observability import ObservabilityMiddleware

# ── Routes ───────────────────────────────────────────────────────────────────
from backend.api.routes import (
    auth,
    signals,
    trades,
    agents,
    analysis,
    analytics,
    backtest,
    backtest_engine,
    research,
    intelligence,
    decision,
    risk,
    self_learning,
    reports,
    institutional,
    institutional_backtest,
    dashboard,
    license,
    trade_report,
    users,
    ai_prediction,
    websocket_routes,          # WebSocket - was missing before
)
from backend.api.observability_routes import router as observability_router

# ── Observability (optional — degraded mode if missing) ──────────────────────
try:
    from backend.observability.metrics import metrics_registry
    from backend.observability.alert_manager import alert_manager
    HAS_OBSERVABILITY = True
except ImportError as exc:
    logger.warning("Observability module not available: %s", exc)
    HAS_OBSERVABILITY = False

# ── DB Pool Monitor (optional) ────────────────────────────────────────────────
try:
    from backend.database.connection_pool_monitor import pool_monitor
    HAS_POOL_MONITOR = True
except ImportError:
    HAS_POOL_MONITOR = False

# ── Institutional (optional — degraded mode if missing) ───────────────────────
try:
    from backend.institutional.data_store import data_store
    HAS_INSTITUTIONAL = True
except ImportError as exc:
    logger.warning("Institutional data store not available: %s", exc)
    HAS_INSTITUTIONAL = False


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown with proper resource management."""
    _start = time.monotonic()
    logger.info("Galaxy Vast AI Trading Platform starting up ...")
    logger.info("Environment : %s", settings.ENVIRONMENT)
    logger.info("Version     : %s", settings.APP_VERSION)

    # Sentry error tracking
    _sentry_dsn = os.getenv("SENTRY_DSN", "")
    if _sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration
            sentry_sdk.init(
                dsn=_sentry_dsn,
                integrations=[
                    FastApiIntegration(transaction_style="endpoint"),
                    LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
                ],
                traces_sample_rate=0.1,
                environment=settings.ENVIRONMENT,
                release=settings.APP_VERSION,
                send_default_pii=False,  # GDPR
            )
            logger.info("Sentry error tracking initialized.")
        except ImportError:
            logger.warning("sentry-sdk not installed. pip install sentry-sdk to enable.")
        except Exception as exc:
            logger.error("Sentry init failed: %s", exc)

    startup_tasks: list[asyncio.Task] = []

    if HAS_POOL_MONITOR:
        startup_tasks.append(asyncio.create_task(
            pool_monitor.start(), name="pool_monitor"
        ))
        logger.info("DB pool monitor started.")

    if HAS_OBSERVABILITY:
        try:
            await alert_manager.register_default_handlers()
            logger.info("Alert manager initialized.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Alert manager init failed: %s", exc)

    if HAS_INSTITUTIONAL:
        try:
            await data_store.initialize()
            logger.info("Institutional data store initialized.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Institutional data store init failed: %s", exc)

    elapsed = time.monotonic() - _start
    logger.info("Startup complete in %.2fs. Ready to accept requests.", elapsed)
    yield

    # ── Shutdown ──
    logger.info("Shutting down ...")
    for task in startup_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Close HTTP client in data_store
    if HAS_INSTITUTIONAL:
        try:
            from backend.institutional.data_store import _http_client
            if _http_client and not _http_client.is_closed:
                await _http_client.aclose()
        except Exception:
            pass

    logger.info("Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description="Institutional-grade AI trading platform with SMC + PA + ML + RL",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# ── CORS (must be outermost — added last, runs first in ASGI stack) ───────────
if "*" in settings.ALLOWED_ORIGINS and settings.ENVIRONMENT == "production":
    logger.critical("CORS wildcard '*' is not allowed in production. Exiting.")
    sys.exit(1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityMiddleware)

# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "path": str(request.url.path)},
    )


# ── Routes ───────────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

for module, _prefix, _tags in [
    (auth,                   "/auth",                 ["Authentication"]),
    (signals,                "/signals",              ["Signals"]),
    (trades,                 "/trades",               ["Trades"]),
    (agents,                 "/agents",               ["Agents"]),
    (analysis,               "/analysis",             ["Analysis"]),
    (analytics,              "/analytics",            ["Analytics"]),
    (backtest,               "/backtest",             ["Backtest"]),
    (backtest_engine,        "/backtest-engine",      ["Backtest Engine"]),
    (research,               "/research",             ["Research"]),
    (intelligence,           "/intelligence",         ["Intelligence"]),
    (decision,               "/decision",             ["Decision"]),
    (risk,                   "/risk",                 ["Risk"]),
    (self_learning,          "/self-learning",        ["Self Learning"]),
    (reports,                "/reports",              ["Reports"]),
    (institutional,          "/institutional",        ["Institutional"]),
    (institutional_backtest, "/institutional-backtest", ["Institutional Backtest"]),
    (dashboard,              "/dashboard",            ["Dashboard"]),
    (license,                "/license",              ["License"]),
    (trade_report,           "/trade-report",         ["Trade Report"]),
    (users,                  "/users",                ["Users"]),
    (ai_prediction,          "/ai-prediction",        ["AI Prediction"]),
]:
    app.include_router(module.router, prefix=PREFIX + _prefix, tags=_tags)

# WebSocket - no /api/v1 prefix
app.include_router(websocket_routes.router, prefix="", tags=["WebSocket"])

# Observability endpoints
app.include_router(observability_router, prefix=PREFIX, tags=["Observability"])


# ── Health Checks ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check for load balancers and monitoring."""
    checks: dict[str, Any] = {}
    overall_healthy = True

    # Database
    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        await asyncio.wait_for(
            asyncio.to_thread(lambda: db.table("system_health").select("id").limit(1).execute()),
            timeout=3.0,
        )
        checks["database"] = {"status": "healthy", "connected": True}
    except asyncio.TimeoutError:
        checks["database"] = {"status": "timeout", "connected": False}
        overall_healthy = False
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": str(exc)[:100]}
        overall_healthy = False

    # Redis
    try:
        from backend.middleware.rate_limit import _get_redis
        r = await _get_redis()
        if r:
            await asyncio.wait_for(r.ping(), timeout=2.0)
            checks["redis"] = {"status": "healthy"}
        else:
            checks["redis"] = {"status": "unavailable", "note": "using in-memory fallback"}
    except Exception as exc:
        checks["redis"] = {"status": "unhealthy", "error": str(exc)[:100]}

    # Observability
    checks["observability"] = {"status": "healthy" if HAS_OBSERVABILITY else "disabled"}

    # Institutional
    checks["institutional"] = {"status": "healthy" if HAS_INSTITUTIONAL else "disabled"}

    # Slow query optimizer (optional)
    try:
        from backend.database.query_optimizer import query_optimizer
        slow_qs = query_optimizer.get_slow_queries(limit=1)
        checks["query_optimizer"] = {"status": "healthy", "slow_queries_sample": len(slow_qs)}
    except Exception:
        checks["query_optimizer"] = {"status": "disabled"}

    # Route count (dynamic)
    _route_count = len([r for r in app.routes if hasattr(r, "methods")])
    checks["routes"] = {"total": _route_count}

    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
            "timestamp": time.time(),
        },
    )


@app.get("/health/live", tags=["Health"])
async def liveness():
    """Kubernetes liveness probe — always returns 200 if process is alive."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Kubernetes readiness probe — checks critical dependencies."""
    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        await asyncio.wait_for(
            asyncio.to_thread(lambda: db.table("system_health").select("id").limit(1).execute()),
            timeout=2.0,
        )
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Not ready: {exc}",
        )


@app.get("/", tags=["Root"])
async def root():
    """Root redirect — returns API info."""
    return {
        "name": "Galaxy Vast AI Trading Platform",
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.ENVIRONMENT != "production" else "disabled in production",
        "health": "/health",
    }
