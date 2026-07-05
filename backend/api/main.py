"""
main.py — FastAPI application entrypoint for GalaxyVast MT5 Trading Bot

Startup sequence:
  1. run_startup_checks()     — Redis, Supabase, MT5 gateway ping
  2. init_redis()             — warm up Redis connection pool
  3. mt5_connector.connect()  — connect to MT5 gateway
  4. signal_processor.register_agents([smc, ml, news])
  5. ml_agent.set_engine(trainer)  — activate ML predictions
  6. Background tasks: stale order cleaner, position reconciler
  7. GracefulDrain SIGTERM handler
"""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GracefulDrain — in-flight request tracking for safe SIGTERM
# ---------------------------------------------------------------------------

class GracefulDrain:
    """Track in-flight requests and wait for them to complete on SIGTERM."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._count: int = 0
        self._timeout = timeout
        self._lock: Optional[asyncio.Lock] = None  # Lazy init — BUG-R6-6 fix
        self._draining = False

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def start_drain(self) -> None:
        self._draining = True
        logger.info("[GracefulDrain] SIGTERM received, waiting for %d in-flight requests", self._count)

    async def enter(self) -> None:
        async with self._get_lock():
            self._count += 1

    async def exit(self) -> None:
        async with self._get_lock():
            self._count -= 1

    async def wait_drain(self) -> None:
        waited = 0.0
        while self._count > 0 and waited < self._timeout:
            await asyncio.sleep(0.5)
            waited += 0.5
        if self._count > 0:
            logger.warning("[GracefulDrain] Timeout after %.1fs, %d requests still in flight", waited, self._count)

    def register_sigterm(self) -> None:
        """Register SIGTERM handler using running loop. BUG-R5-1 fix."""
        try:
            loop = asyncio.get_running_loop()  # NOT get_event_loop()
            def _handler():
                self.start_drain()
                loop.call_soon_threadsafe(
                    lambda: loop.create_task(self.wait_drain())
                )
            loop.add_signal_handler(signal.SIGTERM, _handler)
        except (NotImplementedError, OSError, RuntimeError):
            pass  # Windows / no running loop


_drain = GracefulDrain(timeout=30.0)


# ---------------------------------------------------------------------------
# Background Tasks
# ---------------------------------------------------------------------------

async def _stale_order_cleaner() -> None:
    """Clean up stale orders every 60 seconds. BUG-R4-4 fix."""
    from backend.execution.order_state_machine import order_state_machine
    while True:
        try:
            await asyncio.sleep(60)
            expired = order_state_machine.expire_stale_tickets(max_age_minutes=60)
            if expired:
                logger.warning("[OrderCleaner] Expired %d stale tickets: %s", len(expired), expired)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[OrderCleaner] Error: %s", e)


async def _position_reconciler() -> None:
    """Reconcile OrderStateMachine vs MT5 live positions. BUG-R4-5/ARCH-R5 fix."""
    from backend.execution.mt5_connector import mt5_connector
    from backend.execution.order_state_machine import order_state_machine
    from backend.core.config import get_settings
    settings = get_settings()
    interval = getattr(settings, 'RECONCILE_INTERVAL_SECONDS', 30)
    while True:
        try:
            await asyncio.sleep(interval)
            if not mt5_connector._connected:
                continue
            live: list = await mt5_connector.get_positions()  # BUG-R5-6 fix
            live_tickets = {int(p.get('ticket', 0)) for p in live if p.get('ticket')}
            osm_active = set(order_state_machine.active_tickets())
            # Tickets in OSM but not in MT5 — they've been closed externally
            ghost_tickets = osm_active - live_tickets
            for ticket in ghost_tickets:
                try:
                    order_state_machine.transition(ticket, "CLOSED")
                    logger.info("[Reconciler] Ghost ticket %d closed", ticket)
                except Exception:
                    pass
        except asyncio.CancelledError:
            break
        except AttributeError as e:
            logger.error("[Reconciler] MT5 method missing: %s", e)
        except Exception as e:
            logger.debug("[Reconciler] Error: %s", e)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    logger.info("=" * 60)
    logger.info("GalaxyVast MT5 Trading Bot — Starting Up")
    logger.info("=" * 60)

    # 1. Register graceful drain SIGTERM
    _drain.register_sigterm()

    # 2. Pre-flight checks
    try:
        from backend.startup_check import run_startup_checks
        await run_startup_checks()
    except Exception as e:
        logger.warning("[Startup] Startup checks failed: %s", e)

    # 3. Redis warm-up
    try:
        from backend.database.redis_client import init_redis
        await init_redis()
        logger.info("[Startup] Redis connected")
    except Exception as e:
        logger.warning("[Startup] Redis init failed (non-fatal): %s", e)

    # 4. MT5 Gateway connect  — BUG-R4-2 fix
    try:
        from backend.execution.mt5_connector import mt5_connector
        await mt5_connector.connect()
        logger.info("[Startup] MT5 connector ready (demo=%s)", mt5_connector.demo)
    except Exception as e:
        logger.warning("[Startup] MT5 connect failed (non-fatal): %s", e)

    # 5. Register agents with SignalProcessor  — BUG-R5-4 fix
    try:
        from backend.services.signal_processor import signal_processor
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.ml_agent import MLAgent, ml_agent
        from backend.agents.news_agent import NewsAgent
        _smc = SMCAgent()
        _ml = ml_agent   # Use singleton
        _news = NewsAgent()
        signal_processor.register_agents([_smc, _ml, _news])
        logger.info("[Startup] Agents registered: SMC, ML, News")
    except Exception as e:
        logger.warning("[Startup] Agent registration failed: %s", e)

    # 6. Initialize ML engine  — Phase A fix
    try:
        from backend.agents.ml_agent import ml_agent
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        _trainer = XGBoostTrainer()
        loaded = _trainer.load_model()  # Load saved model if exists
        if loaded:
            ml_agent.set_engine(_trainer)
            logger.info("[Startup] ML engine loaded and active")
        else:
            logger.warning("[Startup] No saved ML model found — MLAgent will ABSTAIN until trained")
    except Exception as e:
        logger.warning("[Startup] ML engine init failed: %s", e)

    # 7. Start background tasks
    _tasks = [
        asyncio.create_task(_stale_order_cleaner()),
        asyncio.create_task(_position_reconciler()),
    ]
    logger.info("[Startup] Background tasks started")

    logger.info("=" * 60)
    logger.info("Startup complete — serving requests")
    logger.info("=" * 60)

    yield  # Application running

    # Shutdown
    logger.info("[Shutdown] Stopping background tasks...")
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)

    # Disconnect MT5
    try:
        from backend.execution.mt5_connector import mt5_connector
        await mt5_connector.disconnect()
    except Exception:
        pass

    # Close Redis
    try:
        from backend.database.redis_client import close_redis
        await close_redis()
    except Exception:
        pass

    logger.info("[Shutdown] Complete")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GalaxyVast MT5 Trading Bot API",
    description="Institutional-grade algorithmic trading system",
    version="12.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS Middleware  — ARCH-R5-6 fix: use ALLOWED_ORIGINS not CORS_ORIGINS
# ---------------------------------------------------------------------------

try:
    from backend.core.config import get_settings
    _settings = get_settings()
    _origins = getattr(_settings, 'ALLOWED_ORIGINS', ["*"])
except Exception:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GracefulDrain Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def drain_middleware(request: Request, call_next):
    """Track in-flight requests for graceful shutdown."""
    if _drain._draining:
        return Response(content="Service shutting down", status_code=503)
    await _drain.enter()
    try:
        return await call_next(request)
    finally:
        await _drain.exit()


# ---------------------------------------------------------------------------
# Health Endpoints
# ---------------------------------------------------------------------------

@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness probe — always returns 200 if server is up."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Readiness probe — checks all dependencies."""
    checks: Dict[str, Any] = {}

    # Redis
    try:
        from backend.database.redis_client import redis_ping
        checks["redis"] = "ok" if await redis_ping() else "degraded"
    except Exception:
        checks["redis"] = "error"

    # MT5
    try:
        from backend.execution.mt5_connector import mt5_connector
        checks["mt5"] = "connected" if mt5_connector._connected else "disconnected"
    except Exception:
        checks["mt5"] = "error"

    # KillSwitch  — BUG-R4-1 fix: is_active not is_active()
    try:
        from backend.risk.kill_switch import kill_switch
        checks["kill_switch"] = "ACTIVE" if kill_switch.is_active else "inactive"
    except Exception:
        checks["kill_switch"] = "unknown"

    # ML Agent
    try:
        from backend.agents.ml_agent import ml_agent
        checks["ml_agent"] = "active" if ml_agent._engine is not None else "no_model"
    except Exception:
        checks["ml_agent"] = "unknown"

    all_ok = all(v in ("ok", "inactive", "connected", "active", "no_model") for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 207,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


# ---------------------------------------------------------------------------
# Router Registration
# ---------------------------------------------------------------------------

def _register_routers() -> None:
    """Register all API routers with graceful ImportError handling."""
    routers = [
        ("backend.api.routes.health", "/api/v1", ["health"]),
        ("backend.api.routes.trading", "/api/v1", ["trading"]),
        ("backend.api.routes.analysis", "/api/v1", ["analysis"]),
        ("backend.api.routes.risk", "/api/v1", ["risk"]),
        ("backend.api.routes.signals", "/api/v1", ["signals"]),
        ("backend.api.routes.positions", "/api/v1", ["positions"]),
        ("backend.api.routes.users", "/api/v1", ["users"]),
        ("backend.api.routes.settings", "/api/v1", ["settings"]),
        ("backend.api.routes.ai_prediction", "/api/v1", ["ai"]),
        ("backend.api.routes.license", "/api/v1", ["license"]),
    ]
    for module_path, prefix, tags in routers:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            router = getattr(mod, 'router', None)
            if router is not None:
                app.include_router(router, prefix=prefix, tags=tags)
        except ImportError as e:
            logger.warning("[Router] Skipped %s: %s", module_path, e)
        except Exception as e:
            logger.error("[Router] Failed to register %s: %s", module_path, e)


_register_routers()
