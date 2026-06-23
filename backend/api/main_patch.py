"""
backend/api/main_patch.py
Phase S -- API Main Hardening Patches

S-5:  Missing /api/v1/learning and /api/v1/portfolio routes -- 404 in production
S-6:  Startup exception swallowed silently -- system starts in broken state
S-7:  /health missing circuit-breaker status
S-8:  No graceful drain on SIGTERM -- in-flight requests dropped
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from typing import Any, Dict

from fastapi import FastAPI

logger = logging.getLogger("api.main_patch")


def register_missing_routes(app: FastAPI) -> None:
    """
    S-5: learning + portfolio routes were never wired in main.py.
    Call once during app creation -- idempotent.
    """
    _V1 = "/api/v1"
    already = {r.path for r in app.routes}  # type: ignore[attr-defined]

    try:
        from backend.api.routes.learning import router as learning_router
        if f"{_V1}/learning" not in already:
            app.include_router(learning_router, prefix=f"{_V1}/learning", tags=["Learning"])
            logger.info("[S-5] Registered /api/v1/learning router")
    except ImportError as exc:
        logger.warning("[S-5] Could not import learning router: %s", exc)

    try:
        from backend.api.routes.portfolio import router as portfolio_router
        if f"{_V1}/portfolio" not in already:
            app.include_router(portfolio_router, prefix=f"{_V1}/portfolio", tags=["Portfolio"])
            logger.info("[S-5] Registered /api/v1/portfolio router")
    except ImportError as exc:
        logger.warning("[S-5] Could not import portfolio router: %s", exc)

    try:
        from backend.api.routes.security_ai import router as sec_ai_router
        if f"{_V1}/security-ai" not in already:
            app.include_router(sec_ai_router, prefix=f"{_V1}/security-ai", tags=["Security AI"])
            logger.info("[S-5] Registered /api/v1/security-ai router")
    except ImportError as exc:
        logger.warning("[S-5] Could not import security-ai router: %s", exc)


async def safe_startup_task(name: str, coro: Any) -> None:
    """
    S-6: Run a startup coroutine; log and re-raise on failure so the
    lifespan context sees the error instead of silently ignoring it.
    """
    try:
        await coro
        logger.info("[Startup] OK %s", name)
    except Exception as exc:
        logger.critical("[Startup] FAILED %s: %s", name, exc, exc_info=True)
        raise RuntimeError(f"Startup task '{name}' failed: {exc}") from exc


def get_circuit_breaker_health() -> Dict[str, Any]:
    """
    S-7: Returns dict of all known breaker states for /health endpoint.
    Fails gracefully if circuit_breaker module unavailable.
    """
    try:
        from backend.circuit_breaker import _REGISTRY  # type: ignore[attr-defined]
        return {
            name: {
                "state": str(breaker.state),
                "failure_count": getattr(breaker, "failure_count", 0),
            }
            for name, breaker in _REGISTRY.items()
        }
    except Exception:
        try:
            from backend.circuit_breaker import get_mt5_breaker
            b = get_mt5_breaker()
            return {"mt5": {"state": str(b.state), "failure_count": b.failure_count}}
        except Exception:
            return {}


class GracefulDrain:
    """
    S-8: Tracks in-flight requests; waits for drain on SIGTERM.
    """

    def __init__(self, drain_timeout: float = 10.0) -> None:
        self._in_flight: int = 0
        self._drain_timeout = drain_timeout
        self._shutdown = False
        self._lock = asyncio.Lock()

    async def enter(self) -> bool:
        async with self._lock:
            if self._shutdown:
                return False
            self._in_flight += 1
            return True

    async def exit(self) -> None:
        async with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    async def drain(self) -> None:
        self._shutdown = True
        deadline = time.monotonic() + self._drain_timeout
        while self._in_flight > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self._in_flight > 0:
            logger.warning("[Drain] %d requests still in-flight after timeout", self._in_flight)

    def register_sigterm(self) -> None:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(
            signal.SIGTERM,
            lambda: asyncio.create_task(self.drain()),
        )


graceful_drain = GracefulDrain(drain_timeout=10.0)
