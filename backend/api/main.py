"""Galaxy Vast AI Trading Platform — FastAPI Application
Production-grade, institutional, zero silent failures.
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

# ── Core ───────────────────────────────────────────────────────────────────
from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

# ── Middleware (hard import — no silent fail) ────────────────────────────────
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
)
from backend.api.observability_routes import router as observability_router

# ── Observability (optional — degraded mode if missing) ─────────────────────
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

# ── Institutional (optional — degraded mode if missing) ─────────────────────
try:
    from backend.institutional.data_store import data_store
    HAS_INSTITUTIONAL = True
except ImportError as exc:
    logger.warning("Institutional data store not available: %s", exc)
    HAS_INSTITUTIONAL = False


# ────────────────────────────────────────────────────────────────────────────
# Lifespan
# ────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown with proper resource management."""
    logger.info("Galaxy Vast AI Trading Platform starting up ...")
    logger.info("Environment : %s", settings.ENVIRONMENT)
    logger.info("Version     : %s", settings.APP_VERSION)

    startup_tasks = []

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

    logger.info("Startup complete. Ready to accept requests.")
    yield

    # ── Shutdown ──
    logger.info("Shutting down ...")
    for task in startup_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete.")


# ────────────────────────────────────────────────────────────────────────────
# App
# ────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description="Institutional-grade algorithmic trading system with AI agents, SMC analysis, and ML prediction.",
    version=getattr(settings, "APP_VERSION", "2.0.0"),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS — never wildcard in production ───────────────────────────────────────────
allowed_origins: List[str] = getattr(
    settings, "ALLOWED_ORIGINS",
    ["http://localhost:3000", "http://localhost:8501"]
)
# Safety: block wildcard in production
if settings.ENVIRONMENT == "production" and "*" in allowed_origins:
    logger.error("ALLOWED_ORIGINS contains '*' in production — refusing to start.")
    sys.exit(1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(auth.router,                   prefix=PREFIX + "/auth",                   tags=["Authentication"])
app.include_router(signals.router,                prefix=PREFIX + "/signals",                tags=["Signals"])
app.include_router(trades.router,                 prefix=PREFIX + "/trades",                 tags=["Trades"])
app.include_router(agents.router,                 prefix=PREFIX + "/agents",                 tags=["Agents"])
app.include_router(analysis.router,               prefix=PREFIX + "/analysis",               tags=["Analysis"])
app.include_router(analytics.router,              prefix=PREFIX + "/analytics",              tags=["Analytics"])
app.include_router(backtest.router,               prefix=PREFIX + "/backtest",               tags=["Backtest"])
app.include_router(backtest_engine.router,        prefix=PREFIX + "/backtest-engine",        tags=["Backtest Engine"])
app.include_router(research.router,               prefix=PREFIX + "/research",               tags=["Research"])
app.include_router(intelligence.router,           prefix=PREFIX + "/intelligence",           tags=["Intelligence"])
app.include_router(decision.router,               prefix=PREFIX + "/decision",               tags=["Decision"])
app.include_router(risk.router,                   prefix=PREFIX + "/risk",                   tags=["Risk"])
app.include_router(self_learning.router,          prefix=PREFIX + "/self-learning",          tags=["Self Learning"])
app.include_router(reports.router,                prefix=PREFIX + "/reports",                tags=["Reports"])
app.include_router(institutional.router,          prefix=PREFIX + "/institutional",          tags=["Institutional"])
app.include_router(institutional_backtest.router, prefix=PREFIX + "/institutional-backtest", tags=["Institutional Backtest"])
app.include_router(dashboard.router,              prefix=PREFIX + "/dashboard",              tags=["Dashboard"])
app.include_router(license.router,                prefix=PREFIX + "/license",                tags=["License"])
app.include_router(trade_report.router,           prefix=PREFIX + "/trade-report",           tags=["Trade Report"])
app.include_router(users.router,                  prefix=PREFIX + "/users",                  tags=["Users"])
app.include_router(ai_prediction.router,          prefix=PREFIX + "/ai",                     tags=["AI Prediction"])
app.include_router(observability_router,          prefix="/observability",                   tags=["Observability"])


# ────────────────────────────────────────────────────────────────────────────
# Exception Handlers — ordered: specific before generic
# ────────────────────────────────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return correct HTTP status codes — do NOT return 500 for 4xx errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors. Never leak stack traces or path to client."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc, exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},  # no path, no trace
    )


# ── Core Endpoints ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Comprehensive health check for load balancers and monitoring."""
    db_ok = False
    db_latency_ms = -1.0
    try:
        from backend.database.connection import get_db_client
        t0 = time.monotonic()
        client = await get_db_client()
        await client.table("signals").select("id").limit(1).execute()
        db_latency_ms = round((time.monotonic() - t0) * 1000, 2)
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check DB ping failed: %s", exc)

    pool_status: dict[str, Any] = {}
    if HAS_POOL_MONITOR:
        try:
            pool_status = pool_monitor.get_status()
        except Exception:  # noqa: BLE001
            pass

    slow_queries: list[Any] = []
    if HAS_OBSERVABILITY:
        try:
            from backend.database.query_optimizer import query_optimizer
            slow_queries = query_optimizer.get_slow_queries(limit=5)
        except Exception:  # noqa: BLE001
            pass

    # Dynamic route count from app.routes
    route_count = len([r for r in app.routes if hasattr(r, "methods")])

    overall = "healthy" if db_ok else "degraded"
    return {
        "status": overall,
        "version": getattr(settings, "APP_VERSION", "2.0.0"),
        "environment": settings.ENVIRONMENT,
        "database": {
            "connected": db_ok,
            "latency_ms": db_latency_ms,
            "pool": pool_status,
        },
        "modules": {
            "observability": HAS_OBSERVABILITY,
            "institutional": HAS_INSTITUTIONAL,
            "pool_monitor": HAS_POOL_MONITOR,
        },
        "routes": {
            "total": route_count,
            "active": route_count,
        },
        "slow_queries_sample": slow_queries,
        "timestamp": time.time(),
    }


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    route_count = len([r for r in app.routes if hasattr(r, "methods")])
    return {
        "name": "Galaxy Vast AI Trading Platform",
        "version": getattr(settings, "APP_VERSION", "2.0.0"),
        "docs": "/docs",
        "health": "/health",
        "routes": f"{route_count} active routes",
    }


# ── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=settings.ENVIRONMENT == "development",
        log_level="info",
        access_log=True,
    )
