"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI Application Entry Point

Routers registered:
  /api/v1/signals       - Signal generation
  /api/v1/trades        - Trade management
  /api/v1/risk          - Risk management v2
  /api/v1/agents        - Multi-agent voting engine
  /api/v1/intelligence  - ML learning system
  /api/v1/self-learning - Self-learning + retraining
  /api/v1/analytics     - Professional analytics (Sharpe/Sortino/...)
  /api/v1/research      - Research (backtest/replay/walk-forward)
  /api/v1/ai            - AI prediction (XGBoost)
  /api/v1/backtest      - Institutional backtesting engine (NEW)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌌 Galaxy Vast AI Trading Platform — Starting...")
    yield
    logger.info("🌌 Galaxy Vast AI Trading Platform — Shutdown complete.")


app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description=(
        "Institutional-Grade AI Trading Ecosystem\n\n"
        "Features: SMC Analysis · AI Prediction · Multi-Agent Voting · "
        "Portfolio Risk · Self-Learning · Analytics · "
        "Institutional Backtest Engine · Market Replay · Walk-Forward"
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Galaxy Vast Support", "url": "https://t.me/GalaxyVast_Support"},
    license_info={"name": "Galaxy Vast Enterprise License"},
)

# ── CORS ──────────────────────────────────────────────────────────────────────
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
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "brand": "Galaxy Vast"},
    )

# ── Register routers ──────────────────────────────────────────────────────────
def _register_routers():
    registered = []
    failed = []

    router_map = {
        "signals":      ("backend.api.routes.signals",      None),
        "trades":       ("backend.api.routes.trades",       None),
        "risk":         ("backend.api.routes.risk",         None),
        "agents":       ("backend.api.routes.agents",       None),
        "intelligence": ("backend.api.routes.intelligence", None),
        "self_learning":("backend.api.routes.self_learning",None),
        "analytics":    ("backend.api.routes.analytics",    None),
        "research":     ("backend.api.routes.research",     None),
        "ai_prediction":("backend.api.routes.ai_prediction",None),
        "backtest":     ("backend.api.routes.backtest_engine", None),  # NEW
    }

    for name, (module_path, _) in router_map.items():
        try:
            import importlib
            mod = importlib.import_module(module_path)
            app.include_router(mod.router)
            registered.append(name)
        except ImportError as e:
            failed.append(f"{name}: {e}")
        except Exception as e:
            failed.append(f"{name}: {e}")

    if registered:
        logger.info(f"✅ Routers registered: {registered}")
    if failed:
        logger.warning(f"⚠️ Routers failed: {failed}")

_register_routers()

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "brand":   "Galaxy Vast AI Trading Platform",
        "version": "2.0.0",
        "status":  "online",
        "modules": [
            "signals", "trades", "risk_v2", "multi_agent",
            "intelligence", "self_learning", "analytics",
            "research", "ai_prediction", "institutional_backtest",
        ],
    }

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "brand": "Galaxy Vast"}
