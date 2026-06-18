"""
faz F+G+H+I - Main FastAPI application
Sentry + RateLimit + CircuitBreaker + Observability + Security + Health
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Observability (faz 9) - import FIRST so logging is set up early
from backend.observability.structured_logger import setup_logging
from backend.observability.metrics import metrics_registry
from backend.observability.alert_manager import alert_manager
from backend.observability import get_logger

logger = get_logger("api.main")

# Sentry (faz F)
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    _SENTRY_OK = True
except ImportError:
    _SENTRY_OK = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    json_logs = os.getenv("JSON_LOGS", "true").lower() == "true"
    setup_logging(level=log_level, json_format=json_logs)
    logger.info("Galaxy Vast AI Trading Bot starting", version="1.0.0")

    # 2. Secret validation (faz 10)
    try:
        from backend.middleware.secret_manager import validate_secrets
        result = validate_secrets()
        if not result.ok:
            logger.error("SECRET VALIDATION FAILED", missing=result.missing_required)
        else:
            logger.info("All required secrets present")
    except Exception as e:
        logger.warning(f"Secret validation skipped: {e}")

    # 3. Sentry
    dsn = os.getenv("SENTRY_DSN", "")
    if dsn and _SENTRY_OK:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FastApiIntegration(), AsyncioIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("ENVIRONMENT", "production"),
            send_default_pii=False,
        )
        logger.info("Sentry initialized")

    # 4. Database pool monitor
    try:
        from backend.database.connection_pool_monitor import pool_monitor
        await pool_monitor.start()
        logger.info("DB pool monitor started")
    except Exception as e:
        logger.warning(f"DB pool monitor skipped: {e}")

    # 5. Circuit breaker patch
    try:
        from backend.analysis import decision_engine_patch  # noqa: F401
        logger.info("Decision engine patch applied")
    except Exception as e:
        logger.warning(f"Decision engine patch skipped: {e}")

    # 6. Alert manager - register Telegram if available
    try:
        from backend.telegram.bot import send_admin_message
        alert_manager.register_telegram(send_admin_message)
        logger.info("Alert manager: Telegram registered")
    except Exception as e:
        logger.warning(f"Alert manager Telegram skipped: {e}")

    # 7. Register Sentry for alerts
    if _SENTRY_OK and dsn:
        alert_manager.register_sentry(sentry_sdk.capture_exception)

    logger.info("Galaxy Vast AI Trading Bot ready")
    yield

    # Shutdown
    logger.info("Shutting down...")
    try:
        from backend.database.connection_pool_monitor import pool_monitor
        await pool_monitor.stop()
    except Exception:
        pass
    logger.info("Shutdown complete")


# App
app = FastAPI(
    title="Galaxy Vast AI Trading Bot",
    version="1.0.0",
    description="AI-powered XAUUSD trading system with SMC + ML",
    lifespan=lifespan,
)

# CORS
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
)
allowed_origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middleware (faz 10) - FIRST
try:
    from backend.middleware.security import SecurityMiddleware
    app.add_middleware(SecurityMiddleware)
except Exception as e:
    logger.warning(f"SecurityMiddleware skipped: {e}")

# Observability middleware (faz 9)
from backend.middleware.observability import ObservabilityMiddleware
app.add_middleware(ObservabilityMiddleware)

# Rate limit middleware (faz F)
try:
    from backend.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except Exception as e:
    logger.warning(f"RateLimitMiddleware skipped: {e}")

# Routers
from backend.api.observability_routes import router as obs_router
app.include_router(obs_router)

try:
    from backend.api.routes.auth import router as auth_router
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
except Exception as e:
    logger.warning(f"auth router skipped: {e}")

try:
    from backend.api.routes.signals import router as signals_router
    app.include_router(signals_router, prefix="/signals", tags=["signals"])
except Exception as e:
    logger.warning(f"signals router skipped: {e}")

try:
    from backend.api.routes.trades import router as trades_router
    app.include_router(trades_router, prefix="/trades", tags=["trades"])
except Exception as e:
    logger.warning(f"trades router skipped: {e}")

try:
    from backend.api.routes.agents import router as agents_router
    app.include_router(agents_router, prefix="/agents", tags=["agents"])
except Exception as e:
    logger.warning(f"agents router skipped: {e}")

try:
    from backend.api.routes.research import router as research_router
    app.include_router(research_router, prefix="/research", tags=["research"])
except Exception as e:
    logger.warning(f"research router skipped: {e}")

try:
    from backend.api.routes.analytics import router as analytics_router
    app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
except Exception as e:
    logger.warning(f"analytics router skipped: {e}")

try:
    from backend.api.routes.intelligence import router as intelligence_router
    app.include_router(intelligence_router, prefix="/intelligence", tags=["intelligence"])
except Exception as e:
    logger.warning(f"intelligence router skipped: {e}")


# Health endpoint
@app.get("/health", tags=["health"])
async def health_check() -> dict:
    from backend.database.connection_health import check_db_health
    from backend.circuit_breaker import _BREAKERS

    db_ok = False
    db_latency_ms = None
    try:
        t0 = time.time()
        db_ok = await check_db_health()
        db_latency_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        logger.error(f"Health check DB error: {e}")

    circuit_breakers = {
        name: {
            "state": cb.state.value if hasattr(cb.state, "value") else str(cb.state),
            "failure_count": cb._failure_count,
        }
        for name, cb in _BREAKERS.items()
    }

    metrics_snap = metrics_registry.snapshot()

    try:
        from backend.database.connection_pool_monitor import pool_monitor
        pool_status = pool_monitor.get_status()
    except Exception:
        pool_status = {}

    # Secret validation status
    try:
        from backend.middleware.secret_manager import validate_secrets
        secret_status = validate_secrets().summary()
    except Exception:
        secret_status = {}

    overall = "healthy" if db_ok else "degraded"

    return {
        "status": overall,
        "database": {
            "connected": db_ok,
            "latency_ms": db_latency_ms,
        },
        "circuit_breakers": circuit_breakers,
        "pool": pool_status,
        "secrets": secret_status,
        "metrics": {
            "http_requests": metrics_snap["counters"].get("http_requests_total", 0),
            "http_errors": metrics_snap["counters"].get("http_errors_total", 0),
            "active_requests": metrics_snap["gauges"].get("http_active_requests", 0),
            "uptime_seconds": metrics_snap.get("uptime_seconds", 0),
        },
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        f"Unhandled exception: {exc}",
        path=str(request.url.path),
        method=request.method,
    )
    metrics_registry.http_errors_total.inc()

    if _SENTRY_OK:
        try:
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "message_fa": "\u062e\u0637\u0627\u06cc \u062f\u0627\u062e\u0644\u06cc \u0633\u0631\u0648\u0631 \u0631\u062e \u062f\u0627\u062f",
        },
    )
