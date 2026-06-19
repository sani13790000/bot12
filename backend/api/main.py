"""
backend/api/main.py
Galaxy Vast AI Trading Platform - FastAPI application entry point.

Production-grade:
  * Structured logging
  * Graceful shutdown (task cancellation + Redis close)
  * Rate-limiter cleanup task started in lifespan
  * Correct Starlette middleware order documented
  * CORS wildcard guard for production
  * expose_headers matches headers actually returned by middleware
  * Docs disabled in production
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

from backend.middleware.security      import SecurityMiddleware
from backend.middleware.rate_limit    import RateLimitMiddleware, start_cleanup_task, close_redis
from backend.middleware.observability import ObservabilityMiddleware

from backend.api.routes import (
    auth, signals, trades, agents, analysis, analytics,
    backtest, backtest_engine, research, intelligence, decision,
    risk, self_learning, reports, institutional, institutional_backtest,
    dashboard, license, trade_report, users, ai_prediction, websocket_routes,
)
from backend.api.observability_routes import router as observability_router

try:
    from backend.observability.metrics       import metrics_registry
    from backend.observability.alert_manager import alert_manager
    HAS_OBSERVABILITY = True
except ImportError as exc:
    logger.warning("Observability not available: %s", exc)
    HAS_OBSERVABILITY = False

try:
    from backend.database.connection_pool_monitor import pool_monitor
    HAS_POOL_MONITOR = True
except ImportError:
    HAS_POOL_MONITOR = False

try:
    from backend.institutional.data_store import data_store
    HAS_INSTITUTIONAL = True
except ImportError as exc:
    logger.warning("Institutional data store not available: %s", exc)
    HAS_INSTITUTIONAL = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown with full resource management.

    Middleware order (outermost to innermost at runtime):
      CORS -> Observability -> RateLimit -> Security

    Starlette processes middleware in REVERSE order of add_middleware():
      last added = outermost (runs first).
    """
    _start = time.monotonic()
    logger.info("Starting - env=%s ver=%s", settings.ENVIRONMENT, settings.APP_VERSION)

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
                send_default_pii=False,
            )
            logger.info("Sentry initialised.")
        except ImportError:
            logger.warning("sentry-sdk not installed.")
        except Exception as exc:
            logger.error("Sentry init failed: %s", exc)

    startup_tasks: list[asyncio.Task] = []
    # Rate-limiter cleanup task - must start here (needs running event loop).
    startup_tasks.append(
        asyncio.create_task(start_cleanup_task(), name="rate_limit_cleanup")
    )

    if HAS_POOL_MONITOR:
        startup_tasks.append(asyncio.create_task(pool_monitor.start(), name="pool_monitor"))
        logger.info("DB pool monitor started.")

    if HAS_OBSERVABILITY:
        try:
            await alert_manager.register_default_handlers()
            logger.info("Alert manager initialised.")
        except Exception as exc:
            logger.error("Alert manager init failed: %s", exc)

    if HAS_INSTITUTIONAL:
        try:
            await data_store.initialize()
            logger.info("Institutional data store initialised.")
        except Exception as exc:
            logger.error("Institutional data store init failed: %s", exc)

    logger.info("Startup complete in %.2fs.", time.monotonic() - _start)
    yield

    # Shutdown
    logger.info("Shutting down ...")
    for task in startup_tasks:
        if not task.done():
            task.cancel()
    if startup_tasks:
        await asyncio.gather(*startup_tasks, return_exceptions=True)

    if HAS_INSTITUTIONAL:
        try:
            from backend.institutional.data_store import _http_client
            if _http_client and not _http_client.is_closed:
                await _http_client.aclose()
        except Exception:
            pass

    await close_redis()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description="Institutional-grade AI trading platform with SMC + PA + ML + RL",
    version=settings.APP_VERSION,
    docs_url    ="/docs"         if settings.ENVIRONMENT != "production" else None,
    redoc_url   ="/redoc"        if settings.ENVIRONMENT != "production" else None,
    openapi_url ="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

if "*" in settings.ALLOWED_ORIGINS and settings.ENVIRONMENT == "production":
    logger.critical("CORS wildcard '*' not allowed in production. Exiting.")
    sys.exit(1)

# Middleware order (Starlette processes in REVERSE order of add_middleware):
# Runtime flow: CORS -> Observability -> RateLimit -> Security -> Handler
# add_middleware order: Security first (innermost), CORS last (outermost)
app.add_middleware(SecurityMiddleware)       # innermost - added first
app.add_middleware(RateLimitMiddleware)      # wraps Security
app.add_middleware(ObservabilityMiddleware)  # wraps RateLimit
app.add_middleware(                          # outermost - added last
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    # Only expose headers that are actually set by our middleware layers:
    expose_headers=[
        "X-Request-ID",           # SecurityMiddleware
        "X-RateLimit-Limit",      # RateLimitMiddleware
        "X-RateLimit-Remaining",  # RateLimitMiddleware
        "X-RateLimit-Window",     # RateLimitMiddleware
        "X-Response-Time",        # SecurityMiddleware
    ],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Never leak 5xx detail to clients.
    detail = exc.detail if exc.status_code < 500 else "Internal server error"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail, "status_code": exc.status_code, "path": str(request.url.path)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled %s %s: %s", request.method, request.url.path, exc, exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "path": str(request.url.path)},
    )


_V1 = "/api/v1"
for _module, _pfx, _tags in [
    (auth,                   "/auth",                   ["Authentication"]),
    (signals,                "/signals",                ["Signals"]),
    (trades,                 "/trades",                 ["Trades"]),
    (agents,                 "/agents",                 ["Agents"]),
    (analysis,               "/analysis",               ["Analysis"]),
    (analytics,              "/analytics",              ["Analytics"]),
    (backtest,               "/backtest",               ["Backtest"]),
    (backtest_engine,        "/backtest-engine",        ["Backtest Engine"]),
    (research,               "/research",               ["Research"]),
    (intelligence,           "/intelligence",           ["Intelligence"]),
    (decision,               "/decision",               ["Decision"]),
    (risk,                   "/risk",                   ["Risk"]),
    (self_learning,          "/self-learning",          ["Self Learning"]),
    (reports,                "/reports",                ["Reports"]),
    (institutional,          "/institutional",          ["Institutional"]),
    (institutional_backtest, "/institutional-backtest", ["Institutional Backtest"]),
    (dashboard,              "/dashboard",              ["Dashboard"]),
    (license,                "/license",                ["License"]),
    (trade_report,           "/trade-report",           ["Trade Report"]),
    (users,                  "/users",                  ["Users"]),
    (ai_prediction,          "/ai-prediction",          ["AI Prediction"]),
]:
    app.include_router(_module.router, prefix=_V1 + _pfx, tags=_tags)

app.include_router(websocket_routes.router, prefix="", tags=["WebSocket"])
app.include_router(observability_router, prefix=_V1, tags=["Observability"])


@app.get("/health/live", tags=["Health"], include_in_schema=False)
async def liveness():
    """Kubernetes liveness probe. Minimal - never rate-limited."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"], include_in_schema=False)
async def readiness():
    """Kubernetes readiness probe. Never rate-limited."""
    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: db.table("system_health").select("id").limit(1).execute()
            ),
            timeout=2.0,
        )
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Not ready",
        ) from exc


@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check. Returns detailed dependency status."""
    checks: dict[str, Any] = {}
    overall = True

    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: db.table("system_health").select("id").limit(1).execute()
            ),
            timeout=3.0,
        )
        checks["database"] = {"status": "healthy"}
    except asyncio.TimeoutError:
        checks["database"] = {"status": "timeout"}
        overall = False
    except Exception:
        checks["database"] = {"status": "unhealthy"}
        overall = False

    try:
        from backend.middleware.rate_limit import _get_redis
        r = await _get_redis()
        if r:
            await asyncio.wait_for(r.ping(), timeout=2.0)
            checks["redis"] = {"status": "healthy"}
        else:
            checks["redis"] = {"status": "degraded", "note": "in-memory fallback"}
    except Exception:
        checks["redis"] = {"status": "unhealthy"}

    checks["observability"] = {"enabled": HAS_OBSERVABILITY}
    checks["institutional"]  = {"enabled": HAS_INSTITUTIONAL}

    try:
        from backend.database.query_optimizer import query_optimizer
        checks["query_optimizer"] = {
            "status": "healthy",
            "slow_count": len(query_optimizer.get_slow_queries(limit=1)),
        }
    except Exception:
        checks["query_optimizer"] = {"status": "disabled"}

    checks["routes"] = {"total": sum(1 for r in app.routes if hasattr(r, "methods"))}

    return JSONResponse(
        status_code=status.HTTP_200_OK if overall else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status":      "healthy" if overall else "degraded",
            "version":     settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "checks":      checks,
            "timestamp":   time.time(),
        },
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "name":    "Galaxy Vast AI Trading Platform",
        "version": settings.APP_VERSION,
        "docs":    "/docs" if settings.ENVIRONMENT != "production" else "disabled",
        "health":  "/health",
    }


if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower(),
    )
