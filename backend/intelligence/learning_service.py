from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)


@dataclass
class LearningEvent:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    signal_features: Dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    timestamp: float = field(default_factory=time.time)


class LearningService:
    """Tracks trading outcomes and adjusts signal weights."""

    def __init__(self, window: int = 100) -> None:
        self._events: List[LearningEvent] = []
        self._window = window
        self._lock = asyncio.Lock()
        self._weights: Dict[str, float] = {}

    async def record(self, event: LearningEvent) -> None:
        async with self._lock:
            self._events.append(event)
            if len(self._events) > self._window:
                self._events.pop(0)
            await self._update_weights()

    async def _update_weights(self) -> None:
        if not self._events:
            return
        wins = [e for e in self._events if e.pnl > 0]
        win_rate = len(wins) / len(self._events)
        self._weights['win_rate'] = win_rate
        _LOG.debug("Learning: win_rate=%.2f events=%d", win_rate, len(self._events))

    def get_weights(self) -> Dict[str, float]:
        return dict(self._weights)

    def recent_events(self, n: int = 10) -> List[LearningEvent]:
        return self._events[-n:]

    def performance_summary(self) -> Dict[str, Any]:
        if not self._events:
            return {"events": 0, "win_rate": 0.0, "avg_pnl": 0.0}
        wins = [e for e in self._events if e.pnl > 0]
        return {
            "events": len(self._events),
            "win_rate": len(wins) / len(self._events),
            "avg_pnl": sum(e.pnl for e in self._events) / len(self._events),
        }


_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _service
    if _service is None:
        _service = LearningService()
    return _service
