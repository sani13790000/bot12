from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class LearningEvent:
    symbol: str
    signal: Dict[str, Any]
    outcome: Optional[str] = None
    pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)


class LearningService:
    """Self-learning service that improves models from trade outcomes."""

    def __init__(self) -> None:
        self._events: List[LearningEvent] = []
        self._enabled = True

    def record_signal(self, symbol: str, signal: Dict[str, Any]) -> str:
        event = LearningEvent(symbol=symbol, signal=signal)
        self._events.append(event)
        return str(len(self._events) - 1)

    def record_outcome(self, event_id: str, outcome: str, pnl: float) -> None:
        try:
            idx = int(event_id)
            if 0 <= idx < len(self._events):
                self._events[idx].outcome = outcome
                self._events[idx].pnl = pnl
        except (ValueError, IndexError):
            pass

    def get_accuracy(self, symbol: Optional[str] = None, n: int = 100) -> float:
        events = self._events[-n:]
        if symbol:
            events = [e for e in events if e.symbol == symbol]
        completed = [e for e in events if e.outcome is not None]
        if not completed:
            return 0.0
        wins = [e for e in completed if e.pnl > 0]
        return len(wins) / len(completed)

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def clear(self) -> None:
        self._events.clear()


_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _service
    if _service is None:
        _service = LearningService()
    return _service
