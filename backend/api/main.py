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

C8 FIX: CORS origins از environment variable خوانده می‌شود.
        در صورت عدم تنظیم → فقط localhost مجاز است.
        allow_origins=["*"] حذف شد.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ── C8 FIX: CORS origins از environment ──────────────────────────────────────────────
def _get_allowed_origins() -> list[str]:
    """
    ALLOWED_ORIGINS را از environment می‌خواند.
    فرمت: رشته‌های comma-separated
    مثال: ALLOWED_ORIGINS="https://app.galaxyvast.com,https://dashboard.galaxyvast.com"

    اگر تنظیم نشده باشد → فقط localhost در development مجاز است.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "")
    if raw.strip():
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        logger.info(f"CORS: {len(origins)} origin(s) from environment")
        return origins

    # fallback: فقط localhost — برای development
    dev_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    logger.warning(
        "CORS: ALLOWED_ORIGINS not set — allowing localhost only. "
        "Set ALLOWED_ORIGINS env var for production."
    )
    return dev_origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌌 Galaxy Vast AI Trading Platform — Starting...")
    yield
    logger.info("🌌 Galaxy Vast AI Trading Platform — Shutdown complete.")


app = FastAPI(
    title="Galaxy Vast AI Trading Platform",
    description=(
        "Institutional-Grade AI Trading Ecosystem\n\n"
        "Features: SMC Analysis \u00b7 AI Prediction \u00b7 Multi-Agent Voting \u00b7 "
        "Portfolio Risk \u00b7 Self-Learning \u00b7 Analytics \u00b7 "
        "Institutional Backtest Engine \u00b7 Market Replay \u00b7 Walk-Forward"
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Galaxy Vast Support", "url": "https://t.me/GalaxyVast_Support"},
    license_info={"name": "Galaxy Vast Enterprise License"},
)

# ── C8 FIX: CORS با whitelist از environment ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-License-Key", "X-Request-ID"],
)

# ── Global error handler ──────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "brand": "Galaxy Vast"},
    )

# ── Register routers ────────────────────────────────────────────────────────────────
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
        "backtest":     ("backend.api.routes.backtest_engine", None),
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
        logger.info(f"\u2705 Routers registered: {registered}")
    if failed:
        logger.warning(f"\u26a0\ufe0f Routers failed: {failed}")

_register_routers()

# ── Health ────────────────────────────────────────────────────────────────────────
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
