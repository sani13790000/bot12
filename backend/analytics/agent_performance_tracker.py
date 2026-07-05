"""
backend/analytics/agent_performance_tracker.py
Galaxy Vast AI Trading Platform
────────────────────────────────────────────────────────────────────────────────
Per-agent vote tracking with ring buffer (maxlen=10_000).

BUG-Q3 FIX: asyncio.Lock() created in __init__ caused DeprecationWarning / RuntimeError
in Python 3.12 when the singleton is imported at module level (before event loop starts).
Now uses a lazy @property: lock is created on first access inside the running event loop.

Usage::

    from backend.analytics.agent_performance_tracker import agent_tracker
    await agent_tracker.record_vote(agent_name="smc", vote="BUY", confidence=0.82)
    perf = agent_tracker.get_agent_performance("smc")
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

_RING_SIZE = 10_000


class AgentPerformanceTracker:
    """
    Thread-safe ring-buffer tracker for agent voting performance.

    Stores up to *ring_size* vote records per agent and exposes
    aggregated statistics used by MetricsEngine and the admin dashboard.
    """

    def __init__(self, ring_size: int = _RING_SIZE) -> None:
        self._ring_size = ring_size
        # BUG-Q3 FIX: do NOT create asyncio.Lock() here — we are at module level
        # before the event loop exists. Use lazy property instead.
        self._lock_obj: Optional[asyncio.Lock] = None
        self._buffers:  Dict[str, Deque[Dict[str, Any]]] = {}
        self._outcome_buffer: Deque[Dict[str, Any]] = deque(maxlen=ring_size)

    # ── Lazy lock (BUG-Q3 fix) ──
    @property
    def _lock(self) -> asyncio.Lock:
        """Create the Lock lazily, inside the running event loop."""
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj

    # ── Public API ──

    async def record_vote(
        self,
        agent_name: str,
        vote: str,
        confidence: float,
        signal_id: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """Record a single agent vote to the in-memory ring buffer."""
        record = {
            "agent":      agent_name,
            "vote":       vote,
            "confidence": confidence,
            "signal_id":  signal_id,
            "outcome":    outcome,
            "ts":         time.monotonic(),
            "ts_iso":     datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            if agent_name not in self._buffers:
                self._buffers[agent_name] = deque(maxlen=self._ring_size)
            self._buffers[agent_name].append(record)
            self._outcome_buffer.append(record)

        # Fire-and-forget DB persist (best-effort)
        asyncio.ensure_future(self._persist_to_db(record))

    async def update_outcome(
        self, signal_id: str, outcome: str
    ) -> None:
        """Update outcome for all votes tied to *signal_id*."""
        async with self._lock:
            for buf in self._buffers.values():
                for rec in buf:
                    if rec.get("signal_id") == signal_id:
                        rec["outcome"] = outcome

    def get_agent_performance(self, agent_name: str) -> Dict[str, Any]:
        """
        Return aggregated stats for one agent.
        Thread-safe read (no lock needed for deque snapshot).
        """
        buf = list(self._buffers.get(agent_name, []))
        return self._aggregate(agent_name, buf)

    def get_all_performance(self) -> List[Dict[str, Any]]:
        """Return stats for every tracked agent."""
        return [
            self._aggregate(name, list(buf))
            for name, buf in self._buffers.items()
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Top-level summary used by MetricsEngine."""
        all_perf = self.get_all_performance()
        total_votes = sum(a["total_votes"] for a in all_perf)
        agents_with_data = [a for a in all_perf if a["total_votes"] > 0]
        if agents_with_data:
            avg_accuracy = sum(a["accuracy"] for a in agents_with_data) / len(agents_with_data)
        else:
            avg_accuracy = 0.0
        return {
            "agents":         all_perf,
            "total_votes":    total_votes,
            "agent_count":    len(all_perf),
            "consensus_rate": round(avg_accuracy, 4),
        }

    # ── Internal ──

    @staticmethod
    def _aggregate(agent_name: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {
                "agent":        agent_name,
                "total_votes":  0,
                "buy_votes":    0,
                "sell_votes":   0,
                "hold_votes":   0,
                "avg_confidence": 0.0,
                "accuracy":     0.0,
                "wins":         0,
                "losses":       0,
            }
        buy   = sum(1 for r in records if r.get("vote", "").upper() == "BUY")
        sell  = sum(1 for r in records if r.get("vote", "").upper() == "SELL")
        hold  = sum(1 for r in records if r.get("vote", "").upper() in ("HOLD", "NO_TRADE"))
        confs = [r["confidence"] for r in records if "confidence" in r]
        resolved = [r for r in records if r.get("outcome") in ("WIN", "LOSS")]
        wins  = sum(1 for r in resolved if r["outcome"] == "WIN")
        losses = len(resolved) - wins
        accuracy = wins / len(resolved) if resolved else 0.0
        return {
            "agent":          agent_name,
            "total_votes":    len(records),
            "buy_votes":      buy,
            "sell_votes":     sell,
            "hold_votes":     hold,
            "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
            "accuracy":       round(accuracy, 4),
            "wins":           wins,
            "losses":         losses,
        }

    async def _persist_to_db(self, record: Dict[str, Any]) -> None:
        """Best-effort DB persist — never raises."""
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            db.table("agent_vote_log").insert({
                "agent_name":  record["agent"],
                "vote":        record["vote"],
                "confidence":  record["confidence"],
                "signal_id":   record.get("signal_id"),
                "outcome":     record.get("outcome"),
                "created_at":  record["ts_iso"],
            }).execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("AgentTracker DB persist skipped: %s", exc)


# ── Singleton ──
agent_tracker = AgentPerformanceTracker()
