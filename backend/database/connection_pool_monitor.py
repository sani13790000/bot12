"""
Phase 8 — Connection Pool Monitor
Monitors Supabase connection health, latency, and pool saturation.
"""
from __future__ import annotations
import asyncio
import time
import logging
from typing import Any, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger("db.pool_monitor")

# How often to run a health ping (seconds)
HEALTH_PING_INTERVAL = 30
# Latency threshold for warning (ms)
LATENCY_WARN_MS = 200.0
# Latency threshold for critical (ms)
LATENCY_CRIT_MS = 500.0


@dataclass
class PoolSnapshot:
    """A point-in-time snapshot of connection health."""
    timestamp: datetime
    latency_ms: float
    is_healthy: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": round(self.latency_ms, 2),
            "is_healthy": self.is_healthy,
            "error": self.error,
        }


class ConnectionPoolMonitor:
    """
    Phase 8 — Connection Pool Monitor

    Runs a background ping every HEALTH_PING_INTERVAL seconds.
    Tracks latency history and emits warnings when latency spikes.
    Provides get_status() for /health endpoint.
    """

    def __init__(self) -> None:
        self._history: list = []  # List[PoolSnapshot], max 100
        self._max_history = 100
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._ping_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("ConnectionPoolMonitor started")

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ConnectionPoolMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Background loop that pings DB every HEALTH_PING_INTERVAL seconds."""
        while self._running:
            try:
                await self._ping()
            except Exception as e:
                logger.error(f"ConnectionPoolMonitor ping error: {e}")
            await asyncio.sleep(HEALTH_PING_INTERVAL)

    async def _ping(self) -> None:
        """Ping the DB and record latency."""
        from backend.database.connection import db  # lazy import to avoid circular
        start = time.perf_counter()
        error_msg = None
        is_healthy = False
        try:
            health = await db.health_check()
            is_healthy = health.get("healthy", False)
            latency_ms = (time.perf_counter() - start) * 1000
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            error_msg = str(e)

        snapshot = PoolSnapshot(
            timestamp=datetime.utcnow(),
            latency_ms=latency_ms,
            is_healthy=is_healthy,
            error=error_msg,
        )

        async with self._lock:
            self._history.append(snapshot)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._ping_count += 1
            self._total_latency_ms += latency_ms
            if not is_healthy or error_msg:
                self._error_count += 1

        # Emit warnings
        if latency_ms > LATENCY_CRIT_MS:
            logger.error(f"CRITICAL DB latency: {latency_ms:.1f}ms (threshold={LATENCY_CRIT_MS}ms)")
        elif latency_ms > LATENCY_WARN_MS:
            logger.warning(f"HIGH DB latency: {latency_ms:.1f}ms (threshold={LATENCY_WARN_MS}ms)")

    async def get_status(self) -> Dict[str, Any]:
        """Return current pool status for /health endpoint."""
        async with self._lock:
            last = self._history[-1] if self._history else None
            avg_latency = self._total_latency_ms / self._ping_count if self._ping_count > 0 else 0.0
            recent = [s.to_dict() for s in self._history[-5:]]  # last 5 snapshots

        return {
            "is_healthy": last.is_healthy if last else False,
            "last_latency_ms": last.latency_ms if last else None,
            "avg_latency_ms": round(avg_latency, 2),
            "ping_count": self._ping_count,
            "error_count": self._error_count,
            "error_rate_pct": round(self._error_count / self._ping_count * 100, 2) if self._ping_count > 0 else 0.0,
            "recent_snapshots": recent,
            "last_checked": last.timestamp.isoformat() if last else None,
        }

    async def ping_once(self) -> Dict[str, Any]:
        """Manual one-shot ping. Returns snapshot dict."""
        await self._ping()
        async with self._lock:
            return self._history[-1].to_dict() if self._history else {}


# Singleton
pool_monitor = ConnectionPoolMonitor()
