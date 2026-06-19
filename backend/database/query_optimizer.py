"""Query optimizer — tracks slow queries for the /health endpoint.

This is a lightweight in-process tracker.  A real implementation would
hook into the database driver.  The stub below is enough to satisfy
the import in main.py and will not cause startup failures.
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

    # ------------------------------------------------------------------
    # Public API used by main.py /health
    # ------------------------------------------------------------------

    def get_slow_queries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the most recent *limit* slow queries (newest first)."""
        items = list(self._slow)
        items.reverse()
        return items[:limit]

    # ------------------------------------------------------------------
    # Recording helpers — call these from anywhere in the codebase
    # ------------------------------------------------------------------

    def record(
        self,
        query: str,
        duration_ms: float,
        table: str = "",
    ) -> None:
        """Record a query execution.  Only stores it if it is slow."""
        if duration_ms >= _SLOW_THRESHOLD_MS:
            self._slow.append(
                {
                    "query": query[:200],  # truncate for safety
                    "table": table,
                    "duration_ms": round(duration_ms, 2),
                    "ts": time.time(),
                }
            )

    def clear(self) -> None:
        """Clear recorded slow queries (useful in tests)."""
        self._slow.clear()


# Module-level singleton used by main.py
query_optimizer = QueryOptimizer()
