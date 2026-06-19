"""Connection pool monitor — tracks Supabase client health.

Designed as an optional background task; degrades gracefully when
not started.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ConnectionPoolMonitor:
    """Lightweight monitor that pings the DB every *interval* seconds."""

    def __init__(self, interval: int = 60) -> None:
        self._interval = interval
        self._running = False
        self._status: Dict[str, Any] = {
            "healthy": True,
            "last_check": None,
            "latency_ms": -1.0,
            "consecutive_failures": 0,
        }

    async def start(self) -> None:  # pragma: no cover
        """Run until cancelled."""
        self._running = True
        logger.info("Pool monitor started (interval=%ds).", self._interval)
        while self._running:
            await self._ping()
            await asyncio.sleep(self._interval)

    async def _ping(self) -> None:
        try:
            from backend.database.connection import get_db_client

            t0 = time.monotonic()
            client = await get_db_client()
            await client.table("signals").select("id").limit(1).execute()
            latency = round((time.monotonic() - t0) * 1000, 2)
            self._status.update(
                healthy=True,
                last_check=time.time(),
                latency_ms=latency,
                consecutive_failures=0,
            )
        except Exception as exc:
            self._status["consecutive_failures"] = (
                self._status["consecutive_failures"] + 1
            )
            self._status["healthy"] = False
            self._status["last_check"] = time.time()
            logger.warning("Pool monitor ping failed: %s", exc)

    def get_status(self) -> Dict[str, Any]:
        """Return latest status snapshot."""
        return dict(self._status)

    def stop(self) -> None:
        self._running = False


# Module-level singleton used by main.py
pool_monitor = ConnectionPoolMonitor(interval=60)
