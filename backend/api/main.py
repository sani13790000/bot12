"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API Entrypoint — Phase J Fix

BUG-J2 FIX: XGBoostTrainer.load_model() in try/except
  - FileNotFoundError on cold start → WARNING + continue (not crash)
  - /health/ready shows ml_model: no_model until first retrain

BUG-J3 FIX: context_enricher.register_engines() with both smc+ml
  - was: only smc_engine registered
  - now: both smc_engine and trainer registered before signal_processor

Previous fixes retained:
  - workers=1 in Dockerfile
  - GracefulDrain middleware
  - asyncio.get_running_loop() in SIGTERM
  - signal_processor.register_agents([smc, ml, news])
  - MLAgent.set_engine() in lifespan
  - retraining_service.start() in lifespan
  - WebSocket broadcasters
  - CSP middleware
"""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.core.config import settings
from backend.core.logger import get_logger
from backend.database.redis_client import get_redis
from backend.risk.kill_switch import get_kill_switch
from backend.startup_check import run_startup_checks

logger = get_logger("api.main")


# ━━━ Graceful Drain Middleware ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class GracefulDrain:
    _lock: asyncio.Lock | None = None
    _draining: bool = False
    _active: int = 0

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def begin_drain(cls) -> None:
        async with cls._get_lock():
            cls._draining = True
        logger.info("[GracefulDrain] draining")

    @classmethod
    def increment(cls) -> None:
        cls._active += 1

    @classmethod
    def decrement(cls) -> None:
        cls._active -= 1

    @classmethod
    async def wait_idle(cls, timeout: float = 30.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while cls._active > 0 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)


async def _drain_middleware(request: Request, call_next):
    if GracefulDrain._draining:
        return Response("Service shutting down", status_code=503)
    GracefulDrain.increment()
    try:
        return await call_next(request)
    finally:
        GracefulDrain.decrement()


async def csp_middleware(request: Request, call_next):
    response = await call_next(request)
    if getattr(settings, "CSP_ENABLED", False):
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' wss:; "
            "frame-ancestors 'none'"
        )
        header_name = (
            "Content-Security-Policy-Report-Only"
            if getattr(settings, "CSP_REPORT_ONLY", False)
            else "Content-Security-Policy"
        )
        response.headers[header_name] = csp
    return response


async def _position_reconciler(connector) -> None:
    from backend.database.redis_client import get_redis as _get_redis
    while True:
        try:
            positions = await connector.get_positions()
            r = await _get_redis()
            if r:
                await r.set("open_positions", str(positions), ex=60)
        except Exception as exc:
            logger.warning("[Reconciler] %s", exc)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("[Lifespan] Starting Galaxy Vast API...")

    # 1. Startup checks
    await run_startup_checks()

    # 2. Redis
    redis = await get_redis()
    if redis:
        logger.info("[Lifespan] Redis connected")

    # 3. MT5 Connector
    from backend.execution.mt5_connector import MT5Connector
    connector = MT5Connector()
    await connector.connect()
    app.state.mt5 = connector

    # 4. SMC Engine
    from backend.analysis.smc_engine import SMCEngine
    smc_engine = SMCEngine()
    app.state.smc_engine = smc_engine
    logger.info("[Lifespan] SMCEngine initialized")

    # 5. XGBoost Trainer — BUG-J2 FIX: no crash on missing model file
    from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
    trainer = XGBoostTrainer()
    try:
        trainer.load_model()
        logger.info("[Lifespan] XGBoostTrainer: model loaded from disk")
    except (FileNotFoundError, OSError) as exc:
        logger.warning(
            "[Lifespan] XGBoostTrainer: no saved model (%s) — "
            "will train from scratch on first retraining cycle", exc
        )
    except Exception as exc:
        logger.error(
            "[Lifespan] XGBoostTrainer: unexpected load error: %s — continuing", exc
        )
    app.state.trainer = trainer

    # 6. ML Agent
    from backend.agents.ml_agent import ml_agent
    ml_agent.set_engine(trainer)
    logger.info("[Lifespan] MLAgent engine set")

    # 7. Context Enricher — BUG-J3 FIX: register both smc + ml engines
    from backend.services.context_enricher import context_enricher
    context_enricher.register_engines(
        smc_engine=smc_engine,
        ml_engine=trainer,
    )
    logger.info("[Lifespan] ContextEnricher: smc_engine + ml_engine registered")

    # 8. Signal Processor
    from backend.services.signal_processor import signal_processor
    from backend.agents.smc_agent import smc_agent
    from backend.agents.news_agent import NewsAgent
    news_agent = NewsAgent()
    signal_processor.register_agents([smc_agent, ml_agent, news_agent])
    signal_processor.register_engines(
        smc_engine=smc_engine,
        ml_engine=trainer,
    )
    logger.info("[Lifespan] SignalProcessor agents registered")

    # 9. Retraining Service
    from backend.self_learning.retraining_service import retraining_service
    await retraining_service.start()
    logger.info("[Lifespan] RetrainingService started")

    # 10. Position Reconciler
    reconciler_task = asyncio.create_task(
        _position_reconciler(connector),
        name="position_reconciler",
    )

    # 11. WebSocket Broadcasters
    try:
        from backend.api.routes.websocket_routes import start_broadcasters
        await start_broadcasters(connector)
        logger.info("[Lifespan] WebSocket broadcasters started")
    except Exception as exc:
        logger.warning("[Lifespan] WebSocket broadcasters not started: %s", exc)

    # 12. SIGTERM handler
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(
        signal.SIGTERM,
        lambda: asyncio.ensure_future(GracefulDrain.begin_drain()),
    )

    logger.info("[Lifespan] Galaxy Vast API ready")
    yield

    # ── Shutdown ──
    logger.info("[Lifespan] Shutting down...")
    await GracefulDrain.begin_drain()
    await GracefulDrain.wait_idle(timeout=30.0)
    reconciler_task.cancel()
    await retraining_service.stop()
    await connector.disconnect()
    if redis:
        await redis.close()
    logger.info("[Lifespan] Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.PRODUCTION else None,
        redoc_url=None,
    )

    app.middleware("http")(_drain_middleware)
    app.middleware("http")(csp_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    from backend.api.routes import (
        analysis, signals, trades, metrics,
        admin, ai_prediction, backtest,
    )
    app.include_router(analysis.router,      prefix="/analysis",   tags=["analysis"])
    app.include_router(signals.router,       prefix="/signals",    tags=["signals"])
    app.include_router(trades.router,        prefix="/trades",     tags=["trades"])
    app.include_router(metrics.router,       prefix="/metrics",    tags=["metrics"])
    app.include_router(admin.router,         prefix="/admin",      tags=["admin"])
    app.include_router(ai_prediction.router, prefix="/ai",         tags=["ai"])
    app.include_router(backtest.router,      prefix="/backtest",   tags=["backtest"])

    try:
        from backend.api.routes.websocket_routes import ws_router
        app.include_router(ws_router)
    except Exception:
        pass

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready():
        checks: dict = {}
        try:
            r = await get_redis()
            checks["redis"] = "ok" if (r and await r.ping()) else "no_connection"
        except Exception:
            checks["redis"] = "error"
        ks = get_kill_switch()
        checks["kill_switch"] = "active" if await ks.is_active() else "ok"
        try:
            from backend.license.engine import license_engine
            stats = license_engine.stats()
            checks["license"] = "ok" if stats.get("secret_configured") else "no_secret"
        except Exception:
            checks["license"] = "error"
        try:
            checks["ml_model"] = "loaded" if app.state.trainer._model is not None else "no_model"
        except Exception:
            checks["ml_model"] = "unknown"
        return {"status": "ready", "checks": checks}

    return app


app = create_app()
