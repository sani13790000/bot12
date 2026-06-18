"""
Phase 8 — Database Hardening
Query Optimizer + Slow Query Detector + Connection Pool Monitor
"""
from __future__ import annotations
import time
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger("db.optimizer")

# Threshold: queries slower than this are logged as slow
SLOW_QUERY_THRESHOLD_MS = 100.0
# Max slow queries to keep in memory
MAX_SLOW_QUERY_LOG = 500


@dataclass
class QueryStats:
    """Statistics for a single query pattern."""
    table: str
    operation: str  # select_one / select_many / insert / update / delete / rpc
    count: int = 0
    total_ms: float = 0.0
    slow_count: int = 0
    error_count: int = 0
    last_called: Optional[datetime] = None

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "operation": self.operation,
            "count": self.count,
            "avg_ms": round(self.avg_ms, 2),
            "total_ms": round(self.total_ms, 2),
            "slow_count": self.slow_count,
            "error_count": self.error_count,
            "last_called": self.last_called.isoformat() if self.last_called else None,
        }


@dataclass
class SlowQueryEntry:
    """A single slow query record."""
    table: str
    operation: str
    duration_ms: float
    filters: Optional[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "operation": self.operation,
            "duration_ms": round(self.duration_ms, 2),
            "filters": self.filters,
            "timestamp": self.timestamp.isoformat(),
        }


class QueryOptimizer:
    """
    Phase 8 — DB Query Optimizer

    Capabilities:
    - Wraps SupabaseManager calls with timing instrumentation
    - Detects slow queries (> SLOW_QUERY_THRESHOLD_MS)
    - Aggregates per-table / per-operation statistics
    - Recommends missing indexes based on slow query patterns
    - get_report() returns full diagnostic report
    """

    def __init__(self) -> None:
        self._stats: Dict[str, QueryStats] = {}  # key = "table:op"
        self._slow_queries: deque = deque(maxlen=MAX_SLOW_QUERY_LOG)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Instrumentation
    # ------------------------------------------------------------------

    async def timed(self, table: str, operation: str, coro, filters: Optional[str] = None):
        """
        Wrap an awaitable with timing.
        Usage:
            result = await optimizer.timed("trades", "select_many", db.select_many(...))
        """
        start = time.perf_counter()
        error = False
        try:
            result = await coro
            return result
        except Exception:
            error = True
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            await self._record(table, operation, elapsed_ms, error, filters)

    def timed_sync(self, table: str, operation: str, fn: Callable, filters: Optional[str] = None):
        """
        Wrap a sync callable with timing.
        """
        start = time.perf_counter()
        error = False
        try:
            result = fn()
            return result
        except Exception:
            error = True
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            # Fire-and-forget for sync contexts
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._record(table, operation, elapsed_ms, error, filters))
                else:
                    loop.run_until_complete(self._record(table, operation, elapsed_ms, error, filters))
            except Exception:
                pass

    async def _record(self, table: str, operation: str, elapsed_ms: float, error: bool, filters: Optional[str]) -> None:
        key = f"{table}:{operation}"
        async with self._lock:
            if key not in self._stats:
                self._stats[key] = QueryStats(table=table, operation=operation)
            s = self._stats[key]
            s.count += 1
            s.total_ms += elapsed_ms
            s.last_called = datetime.utcnow()
            if error:
                s.error_count += 1
            if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
                s.slow_count += 1
                self._slow_queries.append(SlowQueryEntry(
                    table=table,
                    operation=operation,
                    duration_ms=elapsed_ms,
                    filters=filters,
                ))
                logger.warning(
                    f"SLOW QUERY [{elapsed_ms:.1f}ms > {SLOW_QUERY_THRESHOLD_MS}ms] "
                    f"{operation}({table}) filters={filters}"
                )

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def get_report(self) -> Dict[str, Any]:
        """Full diagnostic report."""
        async with self._lock:
            stats_list = [s.to_dict() for s in self._stats.values()]
            slow_list = [e.to_dict() for e in self._slow_queries]

        # Sort by avg_ms descending
        stats_list.sort(key=lambda x: x["avg_ms"], reverse=True)

        recommendations = self._build_recommendations(stats_list, slow_list)

        return {
            "total_query_patterns": len(stats_list),
            "total_slow_queries": len(slow_list),
            "slow_query_threshold_ms": SLOW_QUERY_THRESHOLD_MS,
            "top_slow_patterns": stats_list[:10],
            "recent_slow_queries": slow_list[-20:],
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _build_recommendations(self, stats: List[Dict], slow: List[Dict]) -> List[str]:
        """Build index / optimization recommendations based on patterns."""
        recs = []
        # Tables with high avg_ms
        slow_tables = {s["table"] for s in stats if s["avg_ms"] > SLOW_QUERY_THRESHOLD_MS}
        for table in slow_tables:
            recs.append(f"CREATE INDEX on `{table}` — queries averaging >{SLOW_QUERY_THRESHOLD_MS}ms")

        # Tables with high error rate
        error_tables = {s["table"] for s in stats if s["count"] > 0 and s["error_count"] / s["count"] > 0.05}
        for table in error_tables:
            recs.append(f"Investigate errors on `{table}` — >5% error rate")

        # Composite index candidates (table+operation combos)
        op_counts: Dict[str, int] = defaultdict(int)
        for s in slow:
            op_counts[s["table"]] += 1
        top_slow_tables = sorted(op_counts, key=lambda t: op_counts[t], reverse=True)[:3]
        for table in top_slow_tables:
            recs.append(f"Consider composite index on `{table}` — most frequent slow queries")

        if not recs:
            recs.append("No recommendations — all queries within threshold.")
        return recs

    async def get_stats_summary(self) -> List[Dict[str, Any]]:
        """Return all stats sorted by avg_ms."""
        async with self._lock:
            return sorted(
                [s.to_dict() for s in self._stats.values()],
                key=lambda x: x["avg_ms"],
                reverse=True,
            )

    async def reset(self) -> None:
        """Reset all stats (useful after deployment)."""
        async with self._lock:
            self._stats.clear()
            self._slow_queries.clear()


# Singleton
query_optimizer = QueryOptimizer()
