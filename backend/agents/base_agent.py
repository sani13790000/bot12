"""backend/agents/base_agent.py
Galaxy Vast AI Trading Platform — Enterprise Base Agent

Fix STRESS-1: AgentVote, AgentResult, AgentStatus were missing — VotingEngine
could not import them from base_agent, causing ImportError on startup.
"""
from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

_LOG = logging.getLogger(__name__)


# ─── AgentStatus ─────────────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    """Lifecycle status of a single agent vote."""
    OK    = "ok"
    SKIP  = "skip"
    ERROR = "error"


# ─── AgentVote (per-agent raw vote) ──────────────────────────────────────────

@dataclass
class AgentVote:
    """Raw vote produced by a single agent."""
    agent_id:   str
    direction:  str            # "BUY" | "SELL" | "HOLD"
    confidence: float          # 0.0 – 1.0
    weight:     float = 1.0
    score:      float = 0.0    # weighted score (filled by VotingEngine)
    reason:     str   = ""
    status:     AgentStatus = AgentStatus.OK
    metadata:   Dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_confidence(self) -> float:
        return self.confidence * self.weight


# ─── AgentResult (enriched result from VotingEngine) ─────────────────────────

@dataclass
class AgentResult:
    """Enriched result wrapping a raw AgentVote with agent name and timing."""
    agent_name: str
    vote:       AgentVote
    latency_ms: float = 0.0


# ─── VoteSignal (legacy compat) ───────────────────────────────────────────────

class VoteSignal(str, Enum):
    BUY     = "BUY"
    SELL    = "SELL"
    NEUTRAL = "NEUTRAL"
    ABSTAIN = "ABSTAIN"


# ─── VoteResult (legacy per-agent result) ────────────────────────────────────

@dataclass
class VoteResult:
    agent_id:   str
    signal:     VoteSignal
    confidence: float
    weight:     float
    latency_ms: float = 0.0
    reason:     str   = ""
    metadata:   Dict[str, Any] = field(default_factory=dict)
    error:      Optional[str]  = None

    @property
    def weighted_confidence(self) -> float:
        return self.confidence * self.weight

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id":            self.agent_id,
            "signal":              self.signal.value,
            "confidence":          round(self.confidence, 4),
            "weight":              round(self.weight, 4),
            "weighted_confidence": round(self.weighted_confidence, 4),
            "latency_ms":          round(self.latency_ms, 2),
            "reason":              self.reason,
            "metadata":            self.metadata,
            "error":               self.error,
        }


# ─── BaseAgent ───────────────────────────────────────────────────────────────

class BaseAgent(abc.ABC):
    """Abstract base for all trading agents."""

    agent_id:  str   = "base"
    weight:    float = 1.0
    has_veto:  bool  = False

    def __init__(
        self,
        agent_id: Optional[str]   = None,
        weight:   Optional[float] = None,
    ) -> None:
        if agent_id is not None:
            self.agent_id = agent_id
        if weight is not None:
            self.weight = weight
        self._log = logging.getLogger(f"{__name__}.{self.agent_id}")

    @abc.abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> VoteResult:
        """Analyse market context and return a vote.

        Args:
            context: Market data, account info, risk parameters.

        Returns:
            VoteResult with signal direction, confidence, and reasoning.
        """

    def _emit_metrics(self, result: VoteResult) -> None:
        """Emit vote metrics. Metrics are optional — never crash agent on failure."""
        try:
            from ..observability.metrics import metrics_registry
            metrics_registry.increment(f"agent.{self.agent_id}.votes.{result.signal.value.lower()}")
            metrics_registry.histogram(f"agent.{self.agent_id}.latency_ms", result.latency_ms)
        except Exception as _me:  # noqa: BLE001 — metrics optional, never crash agent
            _LOG.debug("agent_metrics failed agent=%s: %s", self.agent_id, _me)

    async def health(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id, "weight": self.weight, "status": "ok"}
