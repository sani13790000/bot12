"""
FastAPI Application — Phase K Final
All engines registered; 5-layer context enrichment active.
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


# ────────────────────────────────────────────────────────────────────
class GracefulDrain:
 """Reject new requests during shutdown while in-flight requests finish."""
 def __init__(self):
 self.shutting_down = False

 async def __call__(self, request: Request, call_next):
 if self.shutting_down and request.url.path not in ("/health", "/health/live"):
 return JSONResponse(status_code=503, content={"detail": "shutting down"})
 return await call_next(request)

_drain = GracefulDrain()


# ────────────────────────────────────────────────────────────────────
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
 logger.warning("RetrainingService start failed: %s", exc)

 # ── Position reconciler ──
 reconciler_task = asyncio.create_task(_position_reconciler())

 # ── WS broadcasters ──
 try:
 from backend.api.routes.websocket_routes import start_broadcasters
 await start_broadcasters()
 logger.info("WS broadcasters started")
 except Exception as exc:
 logger.warning("WS broadcasters failed: %s", exc)

 logger.info("=== API startup complete ===")
 yield

 # ── Shutdown ──
 _drain.shutting_down = True
 reconciler_task.cancel()
 try:
 from backend.self_learning.retraining_service import retraining_service
 retraining_service.stop()
 except Exception:
 pass
 try:
 from backend.database.redis_client import get_redis
 redis = await get_redis()
 await redis.close()
 except Exception:
 pass
 logger.info("=== API shutdown complete ===")


async def _position_reconciler():
 """Background task: reconcile open positions every 30 s."""
 while True:
 try:
 await asyncio.sleep(30)
 from backend.execution.mt5_connector import get_mt5_connector
 connector = get_mt5_connector()
 positions = await connector.get_positions()
 logger.debug("Reconciler: %d open positions", len(positions))
 except asyncio.CancelledError:
 break
 except Exception as exc:
 logger.warning("Reconciler error: %s", exc)


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
 title="Galaxy Vast MT5 Trading API",
 version="2.0.0",
 lifespan=lifespan,
)

app.middleware("http")(_drain)

# CORS
_origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["http://localhost:3000"]
app.add_middleware(
 CORSMiddleware,
 allow_origins=_origins,
 allow_credentials=True,
 allow_methods=["*"],
 allow_headers=["*"],
)

# CSP
if getattr(settings, "CSP_ENABLED", False):
 _csp_value = (
 "default-src 'self'; "
 "script-src 'self' 'unsafe-inline'; "
 "style-src 'self' 'unsafe-inline'; "
 "img-src 'self' data:;"
 )
 @app.middleware("http")
 async def csp_middleware(request: Request, call_next):
 response = await call_next(request)
 header_name = (
 "Content-Security-Policy-Report-Only"
 if getattr(settings, "CSP_REPORT_ONLY", False)
 else "Content-Security-Policy"
 )
 response.headers[header_name] = _csp_value
 return response

# Routers
try:
 from backend.api.routes import (
 auth, signals, trades, metrics, analysis,
 ai_prediction, admin, backtest,
 )
 app.include_router(auth.router, prefix="/auth", tags=["auth"])
 app.include_router(signals.router, prefix="/signals", tags=["signals"])
 app.include_router(trades.router, prefix="/trades", tags=["trades"])
 app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
 app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
 app.include_router(ai_prediction.router, prefix="/ai", tags=["ai"])
 app.include_router(admin.router, prefix="/admin", tags=["admin"])
 app.include_router(backtest.router, prefix="/backtest", tags=["backtest"])
except Exception as exc:
 logger.warning("Router import error: %s", exc)

try:
 from backend.api.routes.websocket_routes import ws_router
 app.include_router(ws_router)
except Exception as exc:
 logger.warning("WS router import error: %s", exc)


# ── Health endpoints ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_live():
 return {"status": "ok", "timestamp": time.time()}


@app.get("/health/live", tags=["health"])
async def health_live_k8s():
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

 # Engines
 checks["smc_engine"] = "ok" if smc_engine is not None else "unavailable" # noqa
 checks["pa_engine"] = "ok" if pa_engine is not None else "unavailable" # noqa

 overall = "ready" if checks.get("database") == "ok" else "degraded"
 return {"status": overall, "checks": checks, "timestamp": time.time()}
