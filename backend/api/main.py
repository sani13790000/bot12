"""
FastAPI Application — Phase S Final
All engines registered; 5-layer context enrichment active.
trade_history router registered (BUG-Q1 fix)
All 37 routes registered (BUG-S1 fix)
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
class GracefulDrain:
    """Reject new requests during shutdown while in-flight requests finish."""
    def __init__(self):
        self.shutting_down = False

    async def __call__(self, request: Request, call_next):
        if self.shutting_down and request.url.path not in ("/health", "/health/live"):
            return JSONResponse(status_code=503, content={"detail": "shutting down"})
        return await call_next(request)

_drain = GracefulDrain()


# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise all engines and register with enricher + signal processor."""
    from backend.startup_check import run_startup_checks
    await run_startup_checks()

    # ── Redis ──
    try:
        from backend.database.redis_client import get_redis
        await get_redis()
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)

    # ── SMC Engine ──
    smc_engine = None
    try:
        from backend.analysis.smc_engine import SMCEngine
        smc_engine = SMCEngine()
        logger.info("SMCEngine ready")
    except Exception as exc:
        logger.warning("SMCEngine init failed: %s", exc)

    # ── Price Action Engine ──
    pa_engine = None
    try:
        from backend.analysis.price_action_engine import PriceActionEngine
        pa_engine = PriceActionEngine()
        logger.info("PriceActionEngine ready")
    except Exception as exc:
        logger.warning("PriceActionEngine init failed: %s", exc)

    # ── SMC Scoring Engine ──
    smc_scoring_engine = None
    try:
        from backend.analysis.smc_scoring import SMCScoringEngine
        smc_scoring_engine = SMCScoringEngine()
        logger.info("SMCScoringEngine ready")
    except Exception as exc:
        logger.warning("SMCScoringEngine init failed: %s", exc)

    # ── ML Trainer / Prediction ──
    trainer = None
    try:
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        trainer = XGBoostTrainer()
        try:
            trainer.load_model()
            logger.info("XGBoost model loaded")
        except FileNotFoundError:
            logger.warning("No saved XGBoost model — will train on first cycle")
    except Exception as exc:
        logger.warning("XGBoostTrainer init failed: %s", exc)

    # ── MLAgent ──
    try:
        from backend.agents.ml_agent import ml_agent
        if trainer is not None:
            ml_agent.set_engine(trainer)
            logger.info("MLAgent engine set")
    except Exception as exc:
        logger.warning("MLAgent.set_engine failed: %s", exc)

    # ── Context Enricher (5 engines) ──
    try:
        from backend.services.context_enricher import register_engines
        register_engines(
            smc_engine=smc_engine,
            ml_engine=trainer,
            pa_engine=pa_engine,
            smc_scoring_engine=smc_scoring_engine,
        )
        logger.info("ContextEnricher: all 5 engines registered")
    except Exception as exc:
        logger.warning("ContextEnricher registration failed: %s", exc)

    # ── Signal Processor engines ──
    try:
        from backend.services.signal_processor import signal_processor
        signal_processor.register_engines(
            smc_engine=smc_engine,
            ml_engine=trainer,
            pa_engine=pa_engine,
            smc_scoring_engine=smc_scoring_engine,
        )
        logger.info("SignalProcessor engines registered")
    except Exception as exc:
        logger.warning("SignalProcessor.register_engines failed: %s", exc)

    # ── Retraining Service ──
    try:
        from backend.self_learning.retraining_service import retraining_service
        retraining_service.start()
        logger.info("RetrainingService started")
    except Exception as exc:
        logger.warning("RetrainingService.start failed: %s", exc)

    # ── SecurityAIAgent ──
    try:
        from backend.agents.security_ai_agent import security_ai_agent
        await security_ai_agent.start()
        logger.info("SecurityAIAgent started")
    except Exception as exc:
        logger.warning("SecurityAIAgent.start failed: %s", exc)

    # ── WebSocket Broadcasters ──
    try:
        from backend.api.routes.websocket_routes import start_broadcasters
        await start_broadcasters()
        logger.info("WebSocket broadcasters started")
    except Exception as exc:
        logger.warning("WebSocket broadcasters failed: %s", exc)

    logger.info("=== Galaxy Vast AI startup complete ===")
    yield

    # ──────────────────────────────────────
    # Shutdown
    # ──────────────────────────────────────
    _drain.shutting_down = True
    await asyncio.sleep(2)  # drain window

    try:
        from backend.self_learning.retraining_service import retraining_service
        retraining_service.stop()
    except Exception:
        pass

    try:
        from backend.agents.security_ai_agent import security_ai_agent
        await security_ai_agent.stop()
    except Exception:
        pass

    logger.info("=== Galaxy Vast AI shutdown complete ===")


# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    version="3.0.0",
    description="Enterprise MT5 Trading Ecosystem",
    lifespan=lifespan,
)

# ── Middleware ──
app.middleware("http")(_drain)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Route Registration — BUG-S1 FIX
# ALL 37 route files registered (was only 10 before faz S)
# ─────────────────────────────────────────────────────────────────────────────

# ── Group 1: Core (were already registered) ──
try:
    from backend.api.routes import (
        auth, signals, trades, metrics, analysis,
        ai_prediction, admin, backtest,
    )
    app.include_router(auth.router,          prefix="/auth",     tags=["auth"])
    app.include_router(signals.router,       prefix="/signals",  tags=["signals"])
    app.include_router(trades.router,        prefix="/trades",   tags=["trades"])
    app.include_router(metrics.router,       prefix="/metrics",  tags=["metrics"])
    app.include_router(analysis.router,      prefix="/analysis", tags=["analysis"])
    app.include_router(ai_prediction.router, prefix="/ai",       tags=["ai"])
    app.include_router(admin.router,         prefix="/admin",    tags=["admin"])
    app.include_router(backtest.router,      prefix="/backtest", tags=["backtest"])
except Exception as exc:
    logger.warning("Core router import error: %s", exc)

# BUG-Q1 FIX: trade_history router
try:
    from backend.api.routes.trade_history import router as trade_history_router
    app.include_router(trade_history_router, prefix="/trades", tags=["trades"])
except Exception as exc:
    logger.warning("trade_history router error: %s", exc)

# ── Group 2: Dashboard & Analytics (BUG-S1) ──
try:
    from backend.api.routes import dashboard
    app.include_router(dashboard.router, tags=["dashboard"])
except Exception as exc:
    logger.warning("dashboard router error: %s", exc)

try:
    from backend.api.routes import analytics
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
except Exception as exc:
    logger.warning("analytics router error: %s", exc)

try:
    from backend.api.routes import reports
    app.include_router(reports.router, prefix="/reports", tags=["reports"])
except Exception as exc:
    logger.warning("reports router error: %s", exc)

try:
    from backend.api.routes import portfolio
    app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
except Exception as exc:
    logger.warning("portfolio router error: %s", exc)

try:
    from backend.api.routes import trade_report
    app.include_router(trade_report.router, prefix="/trade-reports", tags=["trade-reports"])
except Exception as exc:
    logger.warning("trade_report router error: %s", exc)

# ── Group 3: Risk & Users (BUG-S1) ──
try:
    from backend.api.routes import risk
    app.include_router(risk.router, prefix="/risk", tags=["risk"])
except Exception as exc:
    logger.warning("risk router error: %s", exc)

try:
    from backend.api.routes import users
    app.include_router(users.router, prefix="/users", tags=["users"])
except Exception as exc:
    logger.warning("users router error: %s", exc)

try:
    from backend.api.routes import billing
    app.include_router(billing.router, prefix="/billing", tags=["billing"])
except Exception as exc:
    logger.warning("billing router error: %s", exc)

try:
    from backend.api.routes import license
    app.include_router(license.router, prefix="/license", tags=["license"])
except Exception as exc:
    logger.warning("license router error: %s", exc)

try:
    from backend.api.routes import permissions_routes
    app.include_router(permissions_routes.router, prefix="/permissions", tags=["permissions"])
except Exception as exc:
    logger.warning("permissions router error: %s", exc)

try:
    from backend.api.routes import rate_limit_routes
    app.include_router(rate_limit_routes.router, prefix="/rate-limits", tags=["rate-limits"])
except Exception as exc:
    logger.warning("rate_limit router error: %s", exc)

# ── Group 4: AI & Intelligence (BUG-S1) ──
try:
    from backend.api.routes import self_learning
    app.include_router(self_learning.router, tags=["self-learning"])
except Exception as exc:
    logger.warning("self_learning router error: %s", exc)

try:
    from backend.api.routes import learning
    app.include_router(learning.router, prefix="/learning", tags=["learning"])
except Exception as exc:
    logger.warning("learning router error: %s", exc)

try:
    from backend.api.routes import decision
    app.include_router(decision.router, prefix="/decision", tags=["decision"])
except Exception as exc:
    logger.warning("decision router error: %s", exc)

try:
    from backend.api.routes import intelligence
    app.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
except Exception as exc:
    logger.warning("intelligence router error: %s", exc)

try:
    from backend.api.routes import research
    app.include_router(research.router, prefix="/research", tags=["research"])
except Exception as exc:
    logger.warning("research router error: %s", exc)

# ── Group 5: Agents & Institutional (BUG-S1) ──
try:
    from backend.api.routes import agents
    app.include_router(agents.router, prefix="/agents", tags=["agents"])
except Exception as exc:
    logger.warning("agents router error: %s", exc)

try:
    from backend.api.routes import institutional
    app.include_router(institutional.router, prefix="/institutional", tags=["institutional"])
except Exception as exc:
    logger.warning("institutional router error: %s", exc)

try:
    from backend.api.routes import institutional_backtest
    app.include_router(institutional_backtest.router, prefix="/institutional-backtest", tags=["institutional"])
except Exception as exc:
    logger.warning("institutional_backtest router error: %s", exc)

try:
    from backend.api.routes import backtest_engine
    app.include_router(backtest_engine.router, prefix="/backtest-engine", tags=["backtest"])
except Exception as exc:
    logger.warning("backtest_engine router error: %s", exc)

# ── Group 6: Security & Admin Extended (BUG-S1) ──
try:
    from backend.api.routes import security_ai
    app.include_router(security_ai.router, prefix="/security-ai", tags=["security"])
except Exception as exc:
    logger.warning("security_ai router error: %s", exc)

try:
    from backend.api.routes import security_ai_extended
    app.include_router(security_ai_extended.router, prefix="/security-ai", tags=["security"])
except Exception as exc:
    logger.warning("security_ai_extended router error: %s", exc)

try:
    from backend.api.routes import security_ai_loader
    app.include_router(security_ai_loader.router, prefix="/security-ai", tags=["security"])
except Exception as exc:
    logger.warning("security_ai_loader router error: %s", exc)

try:
    from backend.api.routes import admin_observability
    app.include_router(admin_observability.router, prefix="/admin", tags=["admin"])
except Exception as exc:
    logger.warning("admin_observability router error: %s", exc)

try:
    from backend.api.routes import admin_users
    app.include_router(admin_users.router, prefix="/admin", tags=["admin"])
except Exception as exc:
    logger.warning("admin_users router error: %s", exc)

try:
    from backend.api.routes import audit_routes_v21
    app.include_router(audit_routes_v21.router, prefix="/audit", tags=["audit"])
except Exception as exc:
    logger.warning("audit_routes_v21 router error: %s", exc)

# ── Group 7: Health route file (BUG-S1) ──
try:
    from backend.api.routes import health as health_routes
    app.include_router(health_routes.router, tags=["health"])
except Exception as exc:
    logger.warning("health routes error: %s", exc)

# ── WebSocket ──
try:
    from backend.api.routes.websocket_routes import ws_router
    app.include_router(ws_router)
except Exception as exc:
    logger.warning("WS router import error: %s", exc)


# ── Health endpoints (inline fallback) ─────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    checks: Dict[str, Any] = {}

    # Redis
    try:
        from backend.database.redis_client import get_redis
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    # DB
    try:
        from backend.database.connection import get_db_connection
        conn = await get_db_connection()
        checks["database"] = "ok" if conn else "unavailable"
    except Exception:
        checks["database"] = "unavailable"

    # MT5
    try:
        from backend.execution.mt5_connector import get_mt5_connector
        mt5 = get_mt5_connector()
        checks["mt5"] = "connected" if mt5.is_connected() else "disconnected"
    except Exception:
        checks["mt5"] = "unavailable"

    # License
    try:
        from backend.license.engine import license_engine
        stats = license_engine.stats()
        checks["license"] = "ok" if stats.get("secret_configured") else "no_secret"
    except Exception:
        checks["license"] = "unavailable"

    # ML model status (BUG-P5 from Phase P)
    try:
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        t = XGBoostTrainer()
        checks["ml_model"] = "loaded" if t.is_model_loaded() else "degraded_not_loaded"
    except Exception:
        checks["ml_model"] = "unavailable"

    overall = "ready" if checks.get("database") == "ok" else "degraded"
    return {"status": overall, "checks": checks, "timestamp": time.time()}
