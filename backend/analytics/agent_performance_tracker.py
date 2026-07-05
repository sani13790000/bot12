"""backend/analytics/agent_performance_tracker.py
Phase L — Real agent voting performance tracking.

Replaces MetricsEngine.get_agent_performance() empty stub with:
- In-memory ring buffer per agent (maxlen=10_000)
- Async DB persist of each vote
- Real consensus_rate, accuracy, avg_confidence
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_MAX_RING     = 10_000
_DB_TIMEOUT   = 5.0


class AgentPerformanceTracker:
    """Thread-safe in-memory tracker with async DB persistence."""

    def __init__(self) -> None:
        # ring buffer: agent_id -> deque of vote dicts
        self._rings: Dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_RING))
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Record
    # ------------------------------------------------------------------ #
    async def record_vote(
        self,
        agent_id:   str,
        signal:     str,
        confidence: float,
        correct:    Optional[bool] = None,   # None = unknown until trade closes
        symbol:     str = "",
    ) -> None:
        """Record one vote. correct=None until trade outcome is known."""
        entry = {
            "agent_id":   agent_id,
            "signal":     signal,
            "confidence": confidence,
            "correct":    correct,
            "symbol":     symbol,
            "ts":         datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._rings[agent_id].append(entry)
        asyncio.create_task(self._persist(entry))

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    async def get_agent_performance(self) -> Dict[str, Any]:
        """Real stats per agent from in-memory ring buffer."""
        async with self._lock:
            snapshot = {k: list(v) for k, v in self._rings.items()}

        agents: List[Dict[str, Any]] = []
        total_votes = 0
        total_consensus = 0

        for agent_id, votes in snapshot.items():
            if not votes:
                continue
            n = len(votes)
            total_votes += n

            # Consensus: votes that are not ABSTAIN
            active = [v for v in votes if v["signal"] not in ("ABSTAIN", "NO_TRADE")]
            consensus_rate = len(active) / n if n else 0.0
            total_consensus += len(active)

            # Accuracy: only on votes where correct is known
            known = [v for v in votes if v["correct"] is not None]
            accuracy = sum(1 for v in known if v["correct"]) / len(known) if known else None

            avg_conf = sum(v["confidence"] for v in votes) / n if n else 0.0

            # Signal distribution
            sig_dist: Dict[str, int] = defaultdict(int)
            for v in votes:
                sig_dist[v["signal"]] += 1

            agents.append({
                "agent_id":       agent_id,
                "total_votes":    n,
                "consensus_rate": round(consensus_rate, 4),
                "accuracy":       round(accuracy, 4) if accuracy is not None else None,
                "avg_confidence": round(avg_conf, 4),
                "signal_dist":    dict(sig_dist),
                "last_vote_ts":   votes[-1]["ts"] if votes else None,
            })

        overall_consensus = total_consensus / total_votes if total_votes else 0.0

        return {
            "agents":         agents,
            "total_votes":    total_votes,
            "consensus_rate": round(overall_consensus, 4),
            "tracked_agents": len(agents),
        }

    async def get_summary(self) -> Dict[str, Any]:
        """Compact summary for /admin/metrics/summary."""
        perf = await self.get_agent_performance()
        return {
            "total_votes":    perf["total_votes"],
            "tracked_agents": perf["tracked_agents"],
            "consensus_rate": perf["consensus_rate"],
        }

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    async def _persist(self, entry: Dict[str, Any]) -> None:
        try:
            from backend.database.connection import get_db_client
            db = await get_db_client()
            await asyncio.wait_for(
                asyncio.to_thread(lambda: db.table("agent_votes").insert(entry).execute()),
                timeout=_DB_TIMEOUT,
            )
        except Exception as e:
            log.debug("AgentPerformanceTracker persist: %s", e)


# Module-level singleton
agent_tracker = AgentPerformanceTracker()
