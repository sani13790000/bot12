"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI Application Entry Point — v4.0.0
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("galaxy_vast.api")

# ── Routers ──────────────────────────────────────────────────────────────────
from backend.api.routes.agents                import router as agents_router
from backend.api.routes.ai_prediction         import router as ai_prediction_router
from backend.api.routes.self_learning         import router as self_learning_router
from backend.api.routes.research              import router as research_router
from backend.api.routes.risk                  import router as risk_router
from backend.api.routes.analytics             import router as analytics_router
from backend.api.routes.institutional_backtest import router as institutional_backtest_router


# ── Services ─────────────────────────────────────────────────────────────────
from backend.self_learning.retraining_service import RetrainingService
_retraining_service: RetrainingService = RetrainingService()

from backend.analytics import AnalyticsService
_analytics_service: AnalyticsService = AnalyticsService(db_pool=None)


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌌 Galaxy Vast AI Trading Platform v4.0.0 — starting up")

    await _retraining_service.start()
    logger.info("✅ RetrainingService started")
    logger.info("✅ AnalyticsService ready")
    logger.info("✅ Institutional Backtest Engine ready")

    yield

    await _retraining_service.stop()
    logger.info("🌌 Galaxy Vast — shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description=(
        "Institutional-Grade AI Trading Intelligence System — v4.0.0\n\n"
        "Modules: SMC Engine · Price Action · Multi-Agent Voting · "
        "Portfolio Risk · Institutional Backtest · Walk-Forward · "
        "Monte Carlo · ML Learning · Analytics · Risk Management"
    ),
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "brand": "Galaxy Vast"},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(agents_router)
app.include_router(ai_prediction_router)
app.include_router(self_learning_router)
app.include_router(research_router)
app.include_router(risk_router)
app.include_router(analytics_router)
app.include_router(institutional_backtest_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "brand":  "Galaxy Vast AI Trading Platform",
        "version":"4.0.0",
        "modules": [
            "agents", "ai_prediction", "self_learning",
            "research", "risk", "analytics",
            "institutional_backtest",
        ],
    }


@app.get("/")
async def root():
    return {
        "brand":       "🌌 Galaxy Vast AI Trading Platform",
        "version":     "4.0.0",
        "description": "Institutional-Grade AI Trading Intelligence System",
        "docs":        "/docs",
    }
