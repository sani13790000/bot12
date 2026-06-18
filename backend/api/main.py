import os
import sys
import sentry_sdk
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.logger import get_logger
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.database.connection_pool_monitor import pool_monitor
from backend.database.connection_health import get_db_health
from backend.circuit_breaker import get_breaker_status

# Import routes
from backend.api.routes import (
    auth,
    users,
    trades,
    signals,
    analysis,
    ai_prediction,
    analytics,
    backtest_engine,
    decision,
    research,
    intelligence,
    self_learning,
    agents,
    risk,
    dashboard,
    reports,
    license,
    trade_report,
    institutional_backtest,
)

logger = get_logger("api.main")

# Sentry
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        environment=settings.ENVIRONMENT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start background monitors."""
    logger.info("Starting Galaxy Vast AI API...")
    await pool_monitor.start()
    logger.info("ConnectionPoolMonitor started")
    yield
    logger.info("Shutting down Galaxy Vast AI API...")
    await pool_monitor.stop()


app = FastAPI(
    title="Galaxy Vast AI Trading API",
    description="AI-driven trading analysis and execution API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(
    RateLimitMiddleware,
    redis_url=settings.REDIS_URL,
    default_limit=100,
    default_window=60,
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(ai_prediction.router, prefix="/api/ai", tags=["ai_prediction"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(backtest_engine.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(decision.router, prefix="/api/decision", tags=["decision"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["intelligence"])
app.include_router(self_learning.router, prefix="/api/learning", tags=["self_learning"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(license.router, prefix="/api/license", tags=["license"])
app.include_router(trade_report.router, prefix="/api/trade-report", tags=["trade_report"])
app.include_router(institutional_backtest.router, prefix="/api/institutional", tags=["institutional"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "خطای داخلی سرور رخ داد. تیم فنی مطلع شد.",
            "detail_en": "Internal server error. The technical team has been notified.",
            "path": str(request.url),
        },
    )


@app.get("/health")
async def health_check():
    """Comprehensive health endpoint."""
    db_report = await get_db_health()
    breakers = get_breaker_status()

    overall_healthy = (
        db_report.get("database", {}).get("healthy", False)
        and db_report.get("pool", {}).get("is_healthy", False)
    )

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "version": "2.0.0",
        "database": db_report,
        "circuit_breakers": breakers,
    }


@app.get("/")
async def root():
    return {"message": "Galaxy Vast AI Trading API", "version": "2.0.0"}
