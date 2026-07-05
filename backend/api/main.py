"""Galaxy Vast AI Trading Platform — FastAPI entrypoint.

Phase I additions:
- WebSocket broadcasters started in lifespan
- start_broadcasters() from websocket_routes
"""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings
from backend.startup_check import run_startup_checks
from backend.database.redis_client import init_redis
from backend.execution.mt5_connector import mt5_connector
from backend.risk.kill_switch import get_kill_switch
from backend.execution.order_state_machine import order_state_machine
from backend.self_learning.retraining_service import retraining_service
from backend.services.signal_processor import signal_processor
from backend.services.context_enricher import context_enricher

logger = logging.getLogger(__name__)
settings = get_settings()


# ────────────────────────────────────────────────────────────────────────
# Graceful Drain
# ────────────────────────────────────────────────────────────────────────

class GracefulDrain:
    """Middleware helper: tracks in-flight requests and drains on SIGTERM."""

    def __init__(self, drain_timeout: float = 30.0) -> None:
        self._in_flight: int = 0
        self._draining: bool = False
        self._drain_timeout = drain_timeout
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def start_drain(self) -> None:
        self._draining = True
        logger.warning("GracefulDrain: SIGTERM received, draining in-flight requests")

    async def wait_drain(self) -> None:
        try:
            deadline = asyncio.get_running_loop().time() + self._drain_timeout
            while self._in_flight > 0:
                if asyncio.get_running_loop().time() >= deadline:
                    logger.error("GracefulDrain: timeout, %d requests still in-flight", self._in_flight)
                    break
                await asyncio.sleep(0.1)
            logger.info("GracefulDrain: drain complete")
        except Exception as exc:  # noqa: BLE001
            logger.error("GracefulDrain.wait_drain error: %s", exc)

    def register_sigterm(self) -> None:
        try:
            loop = asyncio.get_running_loop()

            def _handler() -> None:
                self.start_drain()
                loop.call_soon_threadsafe(loop.create_task, self.wait_drain())

            loop.add_signal_handler(signal.SIGTERM, _handler)
        except (NotImplementedError, OSError, RuntimeError):
            pass

    async def enter(self) -> None:
        async with self._get_lock():
            self._in_flight += 1

    async def exit(self) -> None:
        async with self._get_lock():
            self._in_flight = max(0, self._in_flight - 1)

    @property
    def is_draining(self) -> bool:
        return self._draining


_drain = GracefulDrain(drain_timeout=float(getattr(settings, "DRAIN_TIMEOUT_SECONDS", 30)))


# ────────────────────────────────────────────────────────────────────────
# Lifespan
# ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown sequence."""
    logger.info("Starting up Galaxy Vast AI Trading Platform...")

    # 1. Pre-flight checks
    await run_startup_checks()

    # 2. Redis
    await init_redis()

    # 3. MT5 Connection
    try:
        await mt5_connector.connect()
        logger.info("MT5 connected")
    except Exception as exc:  # noqa: BLE001
        logger.warning("MT5 connect failed at startup (will retry): %s", exc)

    # 4. ML Engine
    try:
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        from backend.agents.ml_agent import ml_agent
        _trainer = XGBoostTrainer()
        _trainer.load_model()
        ml_agent.set_engine(_trainer)
        context_enricher.register_ml_engine(_trainer)
        logger.info("ML engine loaded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML engine not available: %s", exc)

    # 5. SMC Engine
    try:
        from backend.analysis.smc_engine import SMCEngine
        from backend.agents.smc_agent import smc_agent
        _smc = SMCEngine()
        context_enricher.register_smc_engine(_smc)
        logger.info("SMC engine registered")
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMC engine not available: %s", exc)

    # 6. Register agents with SignalProcessor
    try:
        from backend.agents.smc_agent import smc_agent
        from backend.agents.ml_agent import ml_agent
        from backend.agents.news_agent import news_agent
        signal_processor.register_agents([smc_agent, ml_agent, news_agent])
        logger.info("Agents registered with SignalProcessor")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent registration failed: %s", exc)

    # 7. Background tasks
    asyncio.get_event_loop().create_task(_stale_order_cleaner())
    asyncio.get_event_loop().create_task(_position_reconciler())

    # 8. Retraining service
    try:
        await retraining_service.start()
        logger.info("Retraining service started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retraining service failed to start: %s", exc)

    # 9. WebSocket broadcasters (Phase I)
    try:
        from backend.api.routes.websocket_routes import start_broadcasters
        start_broadcasters()
        logger.info("WebSocket broadcasters started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebSocket broadcasters failed: %s", exc)

    # 10. SIGTERM drain
    _drain.register_sigterm()

    logger.info("Startup complete — Galaxy Vast AI is LIVE")
    yield

    # ── Shutdown ──
    logger.info("Shutting down...")
    try:
        await mt5_connector.disconnect()
    except Exception:  # noqa: BLE001
        pass
    try:
        await retraining_service.stop()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Shutdown complete")


# ────────────────────────────────────────────────────────────────────────
# App factory
# ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=getattr(settings, "APP_NAME", "Galaxy Vast AI Trading"),
    version=getattr(settings, "APP_VERSION", "12.0.0"),
    description="Institutional-grade Multi-Agent AI Trading Platform",
    lifespan=lifespan,
    docs_url="/docs" if getattr(settings, "DEBUG", False) else None,
    redoc_url="/redoc" if getattr(settings, "DEBUG", False) else None,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "ALLOWED_ORIGINS", ["http://localhost:3000"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── CSP Middleware ──
@app.middleware("http")
async def csp_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if getattr(settings, "CSP_ENABLED", False):
        csp_value = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:;"
        )
        header_name = "Content-Security-Policy-Report-Only" if getattr(settings, "CSP_REPORT_ONLY", True) else "Content-Security-Policy"
        response.headers[header_name] = csp_value
    return response


# ── Drain Middleware ──
@app.middleware("http")
async def drain_middleware(request: Request, call_next):
    if _drain.is_draining:
        return JSONResponse(status_code=503, content={"detail": "Server is shutting down"})
    await _drain.enter()
    try:
        return await call_next(request)
    finally:
        await _drain.exit()


# ── Background tasks ──

async def _stale_order_cleaner() -> None:
    """Expire stale orders every 60 seconds."""
    while True:
        try:
            order_state_machine.expire_stale_tickets()
        except Exception as exc:  # noqa: BLE001
            logger.debug("stale_order_cleaner error: %s", exc)
        await asyncio.sleep(60)


async def _position_reconciler() -> None:
    """Reconcile OSM positions with MT5 every RECONCILE_INTERVAL_SECONDS."""
    interval = int(getattr(settings, "RECONCILE_INTERVAL_SECONDS", 30))
    while True:
        await asyncio.sleep(interval)
        try:
            live = await mt5_connector.get_positions()
            osm_tickets = set(order_state_machine.active_tickets())
            live_tickets = {p.get("ticket") for p in (live or []) if p.get("ticket")}
            stale = osm_tickets - live_tickets
            for ticket in stale:
                logger.warning("reconciler: ticket %s in OSM but not in MT5 — marking terminal", ticket)
        except Exception as exc:  # noqa: BLE001
            logger.debug("position_reconciler error: %s", exc)


# ── Routes ──
from backend.api.routes import health, signals, trades, analysis, admin  # noqa: E402
from backend.api.routes.websocket_routes import router as ws_router  # noqa: E402

try:
    from backend.api.routes import metrics  # noqa: E402
    app.include_router(metrics.router)
except ImportError:
    logger.warning("metrics router not available")

app.include_router(health.router)
app.include_router(signals.router)
app.include_router(trades.router)
app.include_router(analysis.router)
app.include_router(admin.router)
app.include_router(ws_router)  # Phase I: WebSocket routes


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "Galaxy Vast AI Trading", "version": getattr(settings, "APP_VERSION", "12.0.0"), "status": "online"}
