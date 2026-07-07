"""Query optimizer — tracks slow queries for the /health endpoint.

FIXES (Phase L):
- L-5: get_stats_summary() was missing → connection_health.py crash on startup
- L-6: record() truncated at time.t (file was cut off in repo) — completed
- L-7: get_stats_summary() returned raw list; callers expected list of dicts
- L-8: No async wrapper → called with `await` in connection_health → TypeError
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List

_MAX_SLOW_QUERIES = 100
_SLOW_THRESHOLD_MS = 500.0


class QueryOptimizer:
    """Singleton that records slow queries observed by any caller."""

    def __init__(self) -> None:
        self._slow: Deque[Dict[str, Any]] = deque(maxlen=_MAX_SLOW_QUERIES)

    def record(
        self,
        query: str,
        duration_ms: float,
        table: str = "",
    ) -> None:
        """Record a query; only stores if slow. FIX L-6: was truncated."""
        if duration_ms >= _SLOW_THRESHOLD_MS:
            self._slow.append(
                {
                    "query": query[:200],
                    "table": table,
                    "duration_ms": round(duration_ms, 2),
                    "ts": time.time(),
                    "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )

    def get_slow_queries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the most recent *limit* slow queries (newest first)."""
        items = list(self._slow)
        items.reverse()
        return items[:limit]

    async def get_stats_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Async wrapper. FIX L-5+L-7+L-8.
        connection_health.py calls: await query_optimizer.get_stats_summary()
        """
        return self.get_slow_queries(limit=limit)

    def clear(self) -> None:
        self._slow.clear()

    @property
    def count(self) -> int:
        return len(self._slow)


# Module-level singleton
query_optimizer = QueryOptimizer()
