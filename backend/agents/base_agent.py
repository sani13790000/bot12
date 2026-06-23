"""Galaxy Vast AI Trading Platform
BaseAgent v2 — MS-4 + MS-5 timeout & failover support
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from backend.core.logger import get_logger


class AgentStatus(str, Enum):
    OK      = "OK"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    SKIP    = "SKIP"


@dataclass
class AgentVote:
    score:      float
    confidence: float
    direction:  Optional[str]  = None
    status:     AgentStatus    = AgentStatus.OK
    reason:     str            = ""
    metadata:   Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.score      = max(0.0, min(100.0, float(self.score)))
        self.confidence = max(0.0, min(100.0, float(self.confidence)))


@dataclass
class AgentResult:
    agent_name: str
    vote:       AgentVote
    elapsed_ms: float          = 0.0
    error:      Optional[str]  = None


class BaseAgent(ABC):
    """
    Base interface for all trading agents.

    Safety (MS-4 / MS-5):
      run() wraps analyze() with try/except + optional asyncio.wait_for.
      A timeout or crash returns neutral AgentResult — never raises.
    """

    def __init__(self, name: str, weight: float = 1.0, enabled: bool = True) -> None:
        self.name    = name
        self.weight  = max(0.0, float(weight))
        self.enabled = enabled
        self._logger = get_logger(f"agent.{name.lower().replace(' ', '_')}")

    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> AgentVote: ...

    async def run(
        self,
        context:   Dict[str, Any],
        timeout_s: Optional[float] = None,
    ) -> AgentResult:
        if not self.enabled:
            return AgentResult(
                agent_name=self.name,
                vote=AgentVote(score=50.0, confidence=0.0,
                               status=AgentStatus.SKIP, reason="Agent disabled"),
                elapsed_ms=0.0,
            )
        t0 = time.perf_counter()
        try:
            if timeout_s is not None:
                vote = await asyncio.wait_for(self.analyze(context), timeout=timeout_s)
            else:
                vote = await self.analyze(context)
            elapsed = (time.perf_counter() - t0) * 1000
            self._logger.debug("score=%.1f conf=%.1f [%.1fms]",
                               vote.score, vote.confidence, elapsed)
            return AgentResult(agent_name=self.name, vote=vote, elapsed_ms=elapsed)
        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - t0) * 1000
            msg = f"Timeout after {timeout_s}s"
            self._logger.warning("MS-4 %s: %s", self.name, msg)
            return AgentResult(
                agent_name=self.name,
                vote=AgentVote(score=50.0, confidence=0.0, status=AgentStatus.ERROR,
                               reason=msg, direction="NEUTRAL"),
                elapsed_ms=elapsed, error=f"timeout after {timeout_s}s",
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._logger.error("MS-5 %s crash: %s", self.name, exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                vote=AgentVote(score=50.0, confidence=0.0, status=AgentStatus.ERROR,
                               reason=f"Crash: {exc}", direction="NEUTRAL"),
                elapsed_ms=elapsed, error=str(exc),
            )

    def __repr__(self) -> str:
        return (f"<{self.__class__.__name__} name={self.name!r} "
                f"weight={self.weight} enabled={self.enabled}>")
