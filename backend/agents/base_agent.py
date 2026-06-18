"""
Galaxy Vast AI Trading Platform
════════════════════════════════
ماژول: Base Agent Interface — SOLID / ISP / DIP
"""
from __future__ import annotations

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
    """خروجی استاندارد هر Agent — رأی نهایی."""
    score:      float                    # 0–100 امتیاز کلی
    confidence: float                    # 0–100 اطمینان به رأی
    direction:  Optional[str]   = None   # BUY / SELL / NEUTRAL
    status:     AgentStatus     = AgentStatus.OK
    reason:     str             = ""
    metadata:   Dict[str, Any]  = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.score      = max(0.0, min(100.0, float(self.score)))
        self.confidence = max(0.0, min(100.0, float(self.confidence)))


@dataclass
class AgentResult:
    """نتیجه کامل اجرای یک Agent — شامل زمان اجرا."""
    agent_name:   str
    vote:         AgentVote
    elapsed_ms:   float       = 0.0
    error:        Optional[str] = None


class BaseAgent(ABC):
    """
    Interface پایه تمام Agentها.

    قوانین SOLID:
    - SRP: هر Agent فقط یک مسئولیت دارد
    - OCP: باز برای توسعه، بسته برای تغییر
    - ISP: Interface مینیمال — فقط analyze()
    - DIP: وابستگی به abstraction، نه implementation
    """

    def __init__(self, name: str, weight: float = 1.0, enabled: bool = True) -> None:
        self.name    = name
        self.weight  = max(0.0, min(1.0, weight))
        self.enabled = enabled
        self._logger = get_logger(f"agent.{name.lower().replace(' ', '_')}")

    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        """تحلیل context و بازگشت رأی."""
        ...

    async def run(self, context: Dict[str, Any]) -> AgentResult:
        """اجرای agent با اندازه‌گیری زمان و مدیریت خطا."""
        if not self.enabled:
            return AgentResult(
                agent_name=self.name,
                vote=AgentVote(score=50.0, confidence=0.0, status=AgentStatus.SKIP,
                               reason="Agent disabled"),
                elapsed_ms=0.0,
            )
        t0 = time.perf_counter()
        try:
            vote = await self.analyze(context)
            elapsed = (time.perf_counter() - t0) * 1000
            self._logger.debug(f"score={vote.score:.1f} conf={vote.confidence:.1f} [{elapsed:.1f}ms]")
            return AgentResult(agent_name=self.name, vote=vote, elapsed_ms=elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._logger.error(f"Agent error: {exc}")
            return AgentResult(
                agent_name=self.name,
                vote=AgentVote(score=50.0, confidence=0.0, status=AgentStatus.ERROR, reason=str(exc)),
                elapsed_ms=elapsed,
                error=str(exc),
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} weight={self.weight} enabled={self.enabled}>"
