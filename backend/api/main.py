"""
backend/api/main.py
Galaxy Vast AI Trading Platform

FIXES APPLIED:
  BUG-R4-1: init_redis() now exists in redis_client.py -- import works
  BUG-R4-2: kill_switch.is_active (no parentheses -- @property)
  BUG-R4-4: _stale_order_cleaner background task added (expire_stale_tickets every 60s)
  ARCH-R4-5: _position_reconciler background task (RECONCILE_INTERVAL_SECONDS)
  ARCH-R4-6: drain_middleware wraps all requests for GracefulDrain
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings
from backend.core.logger import get_logger

logger = get_logger("api.main")
settings = get_settings()


# -- GracefulDrain -------------------------------------------------------
class GracefulDrain:
    """
    ARCH-R4-6 FIX: Middleware now calls enter()/exit() per request.
    Previously _count was always 0 -- drain was instant and meaningless.
    """
    def __init__(self) -> None:
        self._count = 0
        self._draining = False

    def enter(self) -> None:
        self._count += 1

    def exit(self) -> None:
        self._count = max(0, self._count - 1)

    @property
    def in_flight(self) -> int:
        return self._count

    def start_drain(self) -> None:
        self._draining = True
        logger.info("[GracefulDrain] draining -- in-flight=%d", self._count)

    async def wait_drain(self, timeout_s: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_s
        while self._count > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self._count > 0:
            logger.warning("[GracefulDrain] timeout -- %d request(s) still in-flight", self._count)

    def register_sigterm(self) -> None:
        loop = asyncio.get_event_loop()
        def _handler():
            self.start_drain()
            loop.create_task(self.wait_drain())
        try:
            loop.add_signal_handler(signal.SIGTERM, _handler)
        except (NotImplementedError, OSError):
            pass


_drain = GracefulDrain()


# -- Background tasks ----------------------------------------------------
async def _stale_order_cleaner() -> None:
    """
    BUG-R4-4 FIX: expire_stale_tickets() called every 60s.
    Previously defined in OSM but NEVER called from anywhere.
    """
    while True:
        try:
            await asyncio.sleep(60)
            from backend.execution.order_state_machine import order_state_machine
            expired = order_state_machine.expire_stale_tickets()
            if expired:
                logger.warning("[OSM] expired %d stale order(s)", expired)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("[stale_order_cleaner] %s", exc)


async def _position_reconciler() -> None:
    """
    ARCH-R4-5 FIX: Reconcile OSM state vs live MT5 positions.
    RECONCILE_INTERVAL_SECONDS was in config but never used.
    """
    interval = getattr(settings, "RECONCILE_INTERVAL_SECONDS", 30)
    while True:
        try:
            await asyncio.sleep(interval)
            from backend.execution.mt5_connector import mt5_connector
            from backend.execution.order_state_machine import order_state_machine
            if not mt5_connector._connected:
                continue
            live = await mt5_connector.get_positions()
            live_tickets = {p.ticket for p in live}
            for ticket in list(order_state_machine.active_tickets()):
                if ticket not in live_tickets:
                    try:
                        order_state_machine.transition(ticket, "CLOSED")
                        logger.info("[Reconciler] ticket=%d closed by reconciler", ticket)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("[position_reconciler] %s", exc)


# -- Startup helper -------------------------------------------------------
async def safe_startup_task(name: str, coro) -> None:
    try:
        await coro
        logger.info("[startup] %s OK", name)
    except Exception as exc:
        logger.warning("[startup] %s FAILED (non-fatal): %s", name, exc)


# -- Lifespan -------------------------------------------------------------
@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("[main] starting Galaxy Vast API v%s", getattr(settings, "APP_VERSION", "?"))

    # Startup checks
    try:
        from backend.startup_check import run_startup_checks
        await safe_startup_task("startup_checks", run_startup_checks())
    except ImportError:
        logger.warning("[startup] startup_check module not found")

    # Redis (BUG-R4-1 FIX: init_redis now exists)
    from backend.database.redis_client import init_redis
    await safe_startup_task("redis", init_redis())

    # MT5
    from backend.execution.mt5_connector import mt5_connector
    await safe_startup_task("mt5_connect", mt5_connector.connect())

    # SIGTERM drain
    _drain.register_sigterm()

    # Background tasks (BUG-R4-4 FIX: stale cleaner now running)
    cleaner_task    = asyncio.create_task(_stale_order_cleaner(),  name="stale_order_cleaner")
    reconciler_task = asyncio.create_task(_position_reconciler(), name="position_reconciler")

    logger.info("[main] startup complete")
    yield

    # Shutdown
    logger.info("[main] shutting down")
    for task in (cleaner_task, reconciler_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    _drain.start_drain()
    await _drain.wait_drain(timeout_s=30)

    await mt5_connector.disconnect()

    from backend.database.redis_client import close_redis
    await safe_startup_task("redis_close", close_redis())

    logger.info("[main] shutdown complete")


# -- App factory ----------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version=getattr(settings, "APP_VERSION", "1.0.0"),
        lifespan=lifespan,
        docs_url="/docs" if getattr(settings, "APP_ENV", "production") != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(settings, "CORS_ORIGINS", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ARCH-R4-6 FIX: GracefulDrain middleware actually tracking requests
    @app.middleware("http")
    async def drain_middleware(request: Request, call_next: Callable) -> Response:
        _drain.enter()
        try:
            return await call_next(request)
        finally:
            _drain.exit()

    _register_routes(app)

    @app.get("/health", tags=["Health"])
    async def root_health():
        return {"status": "ok", "version": getattr(settings, "APP_VERSION", "?")}

    @app.get("/health/live", tags=["Health"], summary="Docker liveness probe")
    async def root_liveness():
        return {"status": "alive"}

    @app.get("/status", tags=["Health"])
    async def system_status():
        from backend.execution.mt5_connector import mt5_connector as _mt5
        from backend.risk.kill_switch import kill_switch
        mt5_raw = await _mt5.health_check()
        mt5_ok = mt5_raw.get("ok", False) if isinstance(mt5_raw, dict) else bool(mt5_raw)
        return {
            "mt5": "ok" if mt5_ok else "degraded",
            "mt5_mode": mt5_raw.get("mode", "unknown") if isinstance(mt5_raw, dict) else "?",
            # BUG-R4-2 FIX: is_active is @property -- no ()
            "kill_switch": "ACTIVE" if kill_switch.is_active else "inactive",
            "in_flight_requests": _drain.in_flight,
        }

    return app


def _register_routes(app: FastAPI) -> None:
    _FAILED = []

    def _try(prefix: str, module: str, attr: str = "router") -> None:
        try:
            import importlib
            mod = importlib.import_module(module)
            app.include_router(getattr(mod, attr), prefix=prefix)
        except Exception as exc:
            logger.error("[routes] FAILED %s: %s", prefix, exc)
            _FAILED.append(prefix)

    _try("/api/v1/health",    "backend.api.routes.health")
    _try("/api/v1/signals",   "backend.api.routes.signals")
    _try("/api/v1/risk",      "backend.api.routes.risk")
    _try("/api/v1/trades",    "backend.api.routes.trades")
    _try("/api/v1/auth",      "backend.api.routes.auth")
    _try("/api/v1/dashboard", "backend.api.routes.dashboard")

    if _FAILED:
        logger.warning("[routes] %d failed: %s", len(_FAILED), _FAILED)


app = create_app()
