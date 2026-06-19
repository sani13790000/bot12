"""Galaxy Vast AI Trading Platform — FastAPI Application Entry Point."""

from __future__ import annotations
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ------------------------------------------------------------------ #
#  Observability & Logging (first, before everything)
# ------------------------------------------------------------------ #
try:
    from backend.observability.structured_logger import get_logger, setup_logging
    setup_logging()
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Lifespan (startup / shutdown)
# ------------------------------------------------------------------ #
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Galaxy Vast API starting up...")

    # Secrets validation
    required = ["SUPABASE_URL", "SUPABASE_ANON_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.warning(f"Missing env vars: {missing} — some features will be limited")

    # Sentry
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)
            logger.info("Sentry initialized")
        except Exception as e:
            logger.warning(f"Sentry init failed: {e}")

    # DB pool monitor
    try:
        from backend.database.connection_pool_monitor import ConnectionPoolMonitor
        monitor = ConnectionPoolMonitor()
        app.state.pool_monitor = monitor
        await monitor.start()
        logger.info("DB pool monitor started")
    except Exception as e:
        logger.warning(f"DB pool monitor skipped: {e}")

    # Decision engine patch
    try:
        from backend.analysis.decision_engine_patch import apply_patch
        apply_patch()
        logger.info("Decision engine patch applied")
    except Exception as e:
        logger.warning(f"Decision engine patch skipped: {e}")

    # Alert manager
    try:
        from backend.observability.alert_manager import AlertManager
        alert_mgr = AlertManager()
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            await alert_mgr.register_telegram(telegram_token)
        app.state.alert_manager = alert_mgr
        logger.info("Alert manager initialized")
    except Exception as e:
        logger.warning(f"Alert manager skipped: {e}")

    logger.info("Galaxy Vast API ready 🌌")
    yield

    logger.info("Galaxy Vast API shutting down...")
    try:
        if hasattr(app.state, "pool_monitor"):
            await app.state.pool_monitor.stop()
    except Exception:
        pass


# ------------------------------------------------------------------ #
#  App factory
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description="Institutional-grade AI trading system with 12 modules",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ------------------------------------------------------------------ #
#  CORS
# ------------------------------------------------------------------ #
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
#  Middleware stack (order matters: outermost = last added)
# ------------------------------------------------------------------ #
try:
    from backend.middleware.security import SecurityMiddleware
    app.add_middleware(SecurityMiddleware)
except Exception as e:
    logger.warning(f"SecurityMiddleware skipped: {e}")

try:
    from backend.observability.observability import ObservabilityMiddleware
    app.add_middleware(ObservabilityMiddleware)
except Exception as e:
    logger.warning(f"ObservabilityMiddleware skipped: {e}")

try:
    from backend.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except Exception as e:
    logger.warning(f"RateLimitMiddleware skipped: {e}")

# ------------------------------------------------------------------ #
#  Routes
# ------------------------------------------------------------------ #
routers_to_include = [
    ("backend.api.routes.auth",                  "/api",           ["auth"]),
    ("backend.api.routes.signals",               "/api",           ["signals"]),
    ("backend.api.routes.trades",                "/api",           ["trades"]),
    ("backend.api.routes.agents",                "/api",           ["agents"]),
    ("backend.api.routes.analysis",              "/api",           ["analysis"]),
    ("backend.api.routes.analytics",             "/api",           ["analytics"]),
    ("backend.api.routes.backtest_engine",       "/api",           ["backtest"]),
    ("backend.api.routes.research",              "/api",           ["research"]),
    ("backend.api.routes.intelligence",          "/api",           ["intelligence"]),
    ("backend.api.routes.decision",              "/api",           ["decision"]),
    ("backend.api.routes.risk",                  "/api",           ["risk"]),
    ("backend.api.routes.self_learning",         "/api",           ["self_learning"]),
    ("backend.api.routes.reports",               "/api",           ["reports"]),
    ("backend.api.routes.trade_report",          "/api",           ["trade_report"]),
    ("backend.api.routes.dashboard",             "/api",           ["dashboard"]),
    ("backend.api.routes.ai_prediction",         "/api",           ["ai_prediction"]),
    ("backend.api.routes.users",                 "/api",           ["users"]),
    ("backend.api.routes.license",               "/api",           ["license"]),
    ("backend.api.routes.institutional_backtest","/api",           ["institutional_backtest"]),
    # ★ New institutional modules router
    ("backend.api.routes.institutional",         "",               ["institutional"]),
]

for module_path, prefix, tags in routers_to_include:
    try:
        import importlib
        module = importlib.import_module(module_path)
        router = getattr(module, "router")
        if prefix:
            app.include_router(router, prefix=prefix)
        else:
            app.include_router(router)
        logger.info(f"Router loaded: {module_path}")
    except Exception as e:
        logger.warning(f"Router skipped ({module_path}): {e}")

# Observability routes
try:
    from backend.api.observability_routes import router as obs_router
    app.include_router(obs_router)
except Exception as e:
    logger.warning(f"Observability router skipped: {e}")


# ------------------------------------------------------------------ #
#  Health & Root
# ------------------------------------------------------------------ #
@app.get("/health", tags=["system"])
async def health_check(request: Request):
    """System health check."""
    db_ok = True
    db_latency = 0.0

    try:
        if hasattr(request.app.state, "pool_monitor"):
            status = request.app.state.pool_monitor.get_status()
            db_ok = status.get("is_healthy", True)
            db_latency = status.get("avg_latency_ms", 0.0)
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": "2.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "database": {
            "connected": db_ok,
            "latency_ms": round(db_latency, 2),
        },
        "institutional_modules": 12,
        "api_routes": len(routers_to_include),
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "name": "Galaxy Vast AI Trading Platform",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "institutional": "/institutional/health",
        "dashboard": "http://localhost:8501",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
