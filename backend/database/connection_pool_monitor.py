"""Connection pool monitor — tracks Supabase client health.

FIXES (Phase L):
- L-1: get_status() was sync but called as `await pool_monitor.get_status()`
        in connection_health.py → TypeError. Made async.
- L-2: _ping() called `await client.table(...)` but supabase client is sync
        → wrapped in run_in_executor.
- L-3: consecutive_failures never reset on success (was missing healthy=True branch)
- L-4: last_check stored time.time() float; callers expected ISO string
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
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
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Run until cancelled."""
        self._running = True
        logger.info("Pool monitor started (interval=%ds).", self._interval)
        while self._running:
            await self._ping()
            await asyncio.sleep(self._interval)

    def start_background(self) -> None:
        """Launch as a background task (call from lifespan)."""
        self._task = asyncio.create_task(self.start(), name="pool_monitor")

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _ping(self) -> None:
        """FIX L-2: run sync supabase call in executor."""
        try:
            from backend.database.connection import get_db_client

            t0 = time.monotonic()
            client = await get_db_client()

            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.table("signals").select("id").limit(1).execute(),
                ),
                timeout=5.0,
            )
            latency = round((time.monotonic() - t0) * 1000, 2)
            # FIX L-3: reset failures on success
            self._status.update(
                healthy=True,
                last_check=datetime.now(timezone.utc).isoformat(),
                latency_ms=latency,
                consecutive_failures=0,
            )
        except Exception as exc:
            self._status["consecutive_failures"] = self._status.get("consecutive_failures", 0) + 1
            self._status["healthy"] = False
            self._status["last_check"] = datetime.now(timezone.utc).isoformat()
            logger.warning("Pool monitor ping failed: %s", exc)

    # FIX L-1: make async so `await pool_monitor.get_status()` works
    async def get_status(self) -> Dict[str, Any]:
        """Return latest status snapshot."""
        return dict(self._status)

    def get_status_sync(self) -> Dict[str, Any]:
        """Sync accessor for non-async callers."""
        return dict(self._status)


# Module-level singleton used by main.py
pool_monitor = ConnectionPoolMonitor(interval=60)
