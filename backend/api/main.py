"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: FastAPI Application Entry Point
هدف: راه‌اندازی کامل سرور با تمام سرویس‌ها در lifespan
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..core.logger import get_logger
from ..self_learning import (
    PerformanceTracker,
    RetrainingService,
    TradeDatasetGenerator,
    TrainingPipeline,
)
from ..self_learning.training_pipeline import TrainingConfig

logger = get_logger("api.main")


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — راه‌اندازی و خاموش کردن سرویس‌ها
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """راه‌اندازی تمام سرویس‌ها در startup و خاموش کردن در shutdown."""

    logger.info("🌌 Galaxy Vast AI Trading Platform — Starting up...")

    # ─── PostgreSQL Pool ───
    db_pool = await asyncpg.create_pool(
        dsn         = settings.DATABASE_URL,
        min_size    = 5,
        max_size    = 20,
        command_timeout = 60,
    )
    app.state.db_pool = db_pool
    logger.info("✅ PostgreSQL pool ready")

    # ─── Self-Learning Module ───
    dataset_gen = TradeDatasetGenerator(db_pool=db_pool)
    await dataset_gen.ensure_schema()

    tracker = PerformanceTracker(db_pool=db_pool)
    await tracker.ensure_schema()

    config   = TrainingConfig()
    pipeline = TrainingPipeline(config=config)

    retrain_svc = RetrainingService(
        db_pool             = db_pool,
        dataset_generator   = dataset_gen,
        training_pipeline   = pipeline,
        performance_tracker = tracker,
        symbols             = settings.SYMBOLS,
        retrain_interval_hours = settings.RETRAIN_INTERVAL_HOURS,
        min_new_trades      = settings.RETRAIN_MIN_NEW_TRADES,
    )
    await retrain_svc.ensure_schema()
    await retrain_svc.start()

    app.state.dataset_generator   = dataset_gen
    app.state.performance_tracker = tracker
    app.state.retraining_service  = retrain_svc
    logger.info("✅ Self-Learning Module ready")

    # ─── Telegram Bot ───
    try:
        from ..telegram.bot import GalaxyVastBot
        bot = GalaxyVastBot()
        await bot.start()
        app.state.telegram_bot = bot
        logger.info("✅ Telegram bot ready")
    except Exception as exc:
        logger.error(f"Telegram bot failed: {exc}")

    logger.info("🚀 Galaxy Vast — All systems operational")

    yield   # سرور در حال اجراست

    # ─── Shutdown ───
    logger.info("Galaxy Vast — Shutting down...")

    await retrain_svc.stop()

    if hasattr(app.state, "telegram_bot"):
        await app.state.telegram_bot.stop()

    await db_pool.close()
    logger.info("Galaxy Vast — Shutdown complete")


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Galaxy Vast AI Trading Platform",
    description = "Institutional-Grade AI Trading Intelligence System",
    version     = "2.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code = 500,
        content     = {
            "error":   "Internal Server Error",
            "message": str(exc),
            "brand":   "Galaxy Vast AI Trading Platform",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

from .routes.ai_prediction  import router as ai_prediction_router
from .routes.analysis       import router as analysis_router
from .routes.intelligence   import router as intelligence_router
from .routes.research       import router as research_router
from .routes.self_learning  import router as self_learning_router

app.include_router(analysis_router)
app.include_router(ai_prediction_router)
app.include_router(intelligence_router)
app.include_router(research_router)
app.include_router(self_learning_router)


# ─── Health Check ────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {
        "status":  "operational",
        "brand":   "Galaxy Vast AI Trading Platform",
        "version": "2.0.0",
        "modules": {
            "self_learning": True,
            "ai_prediction": True,
            "backtest":      True,
            "telegram":      True,
        },
    }


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "platform": "Galaxy Vast AI Trading Platform",
        "version":  "2.0.0",
        "docs":     "/docs",
        "status":   "operational",
    }
