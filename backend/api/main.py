"""FastAPI entrypoint — Production-grade with full Phase F engine injection."""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graceful drain
# ---------------------------------------------------------------------------

class GracefulDrain:
    def __init__(self) -> None:
        self._count: int = 0
        self._draining: bool = False
        self._lock: Optional[asyncio.Lock] = None   # lazy init

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def enter(self) -> None:
        async with self._get_lock():
            self._count += 1

    async def exit(self) -> None:
        async with self._get_lock():
            self._count = max(0, self._count - 1)

    def start_drain(self) -> None:
        self._draining = True
        logger.info("[GracefulDrain] draining started, in_flight=%d", self._count)

    async def wait_drain(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while self._count > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self._count > 0:
            logger.warning(
                "[GracefulDrain] timeout: %d requests still in flight", self._count
            )
        else:
            logger.info("[GracefulDrain] drain complete")

    def register_sigterm(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            def _handler() -> None:
                self.start_drain()
                loop.call_soon_threadsafe(
                    loop.create_task, self.wait_drain()
                )
            loop.add_signal_handler(signal.SIGTERM, _handler)
        except (NotImplementedError, OSError, RuntimeError):
            pass


_drain = GracefulDrain()


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

async def safe_startup_task(name: str, coro: Any) -> bool:
    try:
        if asyncio.iscoroutine(coro):
            await coro
        return True
    except Exception as exc:
        logger.warning("[Startup] %s failed (non-fatal): %s", name, exc)
        return False


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""

    # ── 1. Config validation ───────────────────────────────────────────
    logger.info("[Startup] ENV=%s", settings.ENVIRONMENT)

    # ── 2. Startup checks ─────────────────────────────────────────────
    try:
        from backend.startup_check import run_startup_checks
        await run_startup_checks()
    except Exception as exc:
        logger.warning("[Startup] startup checks failed: %s", exc)

    # ── 3. Redis ──────────────────────────────────────────────────────
    try:
        from backend.database.redis_client import init_redis
        await safe_startup_task("redis", init_redis())
    except Exception as exc:
        logger.warning("[Startup] redis init failed: %s", exc)

    # ── 4. MT5 Connector ─────────────────────────────────────────────
    mt5_connector = None
    try:
        from backend.execution.mt5_connector import mt5_connector as _mt5
        await _mt5.connect()
        mt5_connector = _mt5
        logger.info("[Startup] MT5 connected demo=%s", _mt5.demo)
    except Exception as exc:
        logger.warning("[Startup] MT5 connect failed: %s", exc)

    # ── 5. SMC Engine ─────────────────────────────────────────────────
    smc_engine = None
    try:
        from backend.analysis.smc_engine import SMCEngine
        smc_engine = SMCEngine()
        logger.info("[Startup] SMCEngine ready")
    except Exception as exc:
        logger.warning("[Startup] SMCEngine init failed: %s", exc)

    # ── 6. ML Engine (XGBoost) ────────────────────────────────────────
    ml_engine = None
    try:
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        _trainer = XGBoostTrainer()
        _trainer.load_model()   # load saved model if exists
        ml_engine = _trainer
        logger.info("[Startup] XGBoostTrainer loaded")
    except Exception as exc:
        logger.warning("[Startup] XGBoostTrainer load failed: %s", exc)

    # ── 7. Inject engines into ContextEnricher via SignalProcessor ────
    try:
        from backend.services.signal_processor import signal_processor
        signal_processor.register_engines(
            smc_engine=smc_engine,
            ml_engine=ml_engine,
        )
        logger.info("[Startup] ContextEnricher engines injected")
    except Exception as exc:
        logger.warning("[Startup] engine injection failed: %s", exc)

    # ── 8. Register Agents ────────────────────────────────────────────
    try:
        from backend.services.signal_processor import signal_processor
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.ml_agent import MLAgent, ml_agent
        from backend.agents.liquidity_agent import LiquidityAgent
        from backend.agents.market_structure_agent import MarketStructureAgent
        from backend.agents.execution_agent import ExecutionAgent

        # Inject ML engine into MLAgent
        if ml_engine is not None:
            ml_agent.set_engine(ml_engine)
            logger.info("[Startup] MLAgent engine set")

        signal_processor.register_agents([
            SMCAgent(),
            ml_agent,
            LiquidityAgent(),
            MarketStructureAgent(),
            ExecutionAgent(),
        ])
        logger.info("[Startup] 5 agents registered")
    except Exception as exc:
        logger.warning("[Startup] agent registration failed: %s", exc)

    # ── 9. Retraining Service ─────────────────────────────────────────
    try:
        from backend.self_learning.retraining_service import retraining_service
        if ml_engine is not None:
            retraining_service.set_trainer(ml_engine)
        await retraining_service.start()
        logger.info("[Startup] RetrainingService started")
    except Exception as exc:
        logger.warning("[Startup] RetrainingService start failed: %s", exc)

    # ── 10. Background tasks ──────────────────────────────────────────
    async def _stale_order_cleaner() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                from backend.execution.order_state_machine import order_state_machine
                order_state_machine.expire_stale_tickets()
            except Exception as exc:
                logger.warning("[OSM] expire_stale_tickets: %s", exc)

    async def _position_reconciler() -> None:
        interval = getattr(settings, "RECONCILE_INTERVAL_SECONDS", 30)
        while True:
            await asyncio.sleep(interval)
            try:
                from backend.execution.mt5_connector import mt5_connector as _c
                from backend.execution.order_state_machine import order_state_machine
                if not _c._connected:
                    continue
                live = await _c.get_positions()
                live_tickets = {int(p.get("ticket", 0)) for p in live}
                osm_tickets  = set(order_state_machine.active_tickets())
                ghost = osm_tickets - live_tickets
                if ghost:
                    logger.warning("[Reconciler] ghost tickets: %s", ghost)
            except Exception as exc:
                logger.debug("[Reconciler] %s", exc)

    asyncio.create_task(_stale_order_cleaner(), name="stale_order_cleaner")
    asyncio.create_task(_position_reconciler(), name="position_reconciler")

    # ── 11. SIGTERM handler ───────────────────────────────────────────
    _drain.register_sigterm()

    logger.info("[Startup] ✅ All systems ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("[Shutdown] starting")
    try:
        from backend.self_learning.retraining_service import retraining_service
        await retraining_service.stop()
    except Exception:
        pass
    try:
        from backend.execution.mt5_connector import mt5_connector as _c
        await _c.disconnect()
    except Exception:
        pass
    try:
        from backend.database.redis_client import close_redis
        await close_redis()
    except Exception:
        pass
    logger.info("[Shutdown] complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    _app = FastAPI(
        title="GalaxyVast MT5 Trading API",
        version="12.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(settings, "ALLOWED_ORIGINS", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # CSP middleware
    if getattr(settings, "CSP_ENABLED", False):
        csp_value = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:;"
        )
        @_app.middleware("http")
        async def csp_middleware(request: Request, call_next: Callable) -> Response:
            response = await call_next(request)
            response.headers["Content-Security-Policy"] = csp_value
            return response

    # Drain middleware
    @_app.middleware("http")
    async def drain_middleware(request: Request, call_next: Callable) -> Response:
        if _drain._draining:
            return JSONResponse(
                {"detail": "server is draining"},
                status_code=503,
            )
        await _drain.enter()
        try:
            return await call_next(request)
        finally:
            await _drain.exit()

    # Routers
    try:
        from backend.api.routes import health, trading, analysis, admin
        _app.include_router(health.router,    prefix="/api/v1")
        _app.include_router(trading.router,   prefix="/api/v1")
        _app.include_router(analysis.router,  prefix="/api/v1")
        _app.include_router(admin.router,     prefix="/api/v1/admin")
    except Exception as exc:
        logger.error("[App] router registration failed: %s", exc)

    @_app.get("/health/live")
    async def liveness() -> dict:
        return {"status": "ok", "time": time.time()}

    return _app


app = create_app()
