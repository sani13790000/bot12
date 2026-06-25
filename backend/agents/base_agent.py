from __future__ import annotations
import abc, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from ..core.logger import get_logger

class VoteSignal(str, Enum):
    BUY     = 'BUY'
    SELL    = 'SELL'
    NEUTRAL = 'NEUTRAL'
    ABSTAIN = 'ABSTAIN'

@dataclass
class VoteResult:
    agent_id:   str
    signal:     VoteSignal
    confidence: float
    weight:     float
    latency_ms: float = 0.0
    reason:     str  = ''
    metadata:   Dict[str, Any] = field(default_factory=dict)
    error:      Optional[str]  = None
    @property
    def weighted_confidence(self) -> float: return self.confidence * self.weight
    def to_dict(self) -> Dict[str, Any]:
        return {'agent_id': self.agent_id, 'signal': self.signal.value, 'confidence': round(self.confidence, 4), 'weight': round(self.weight, 4), 'weighted_confidence': round(self.weighted_confidence, 4), 'latency_ms': round(self.latency_ms, 2), 'reason': self.reason, 'metadata': self.metadata, 'error': self.error}

class BaseAgent(abc.ABC):
    DEFAULT_WEIGHT: float = 1.0
    _SLOW_THRESHOLD_MS: float = 500.0
    def __init__(self) -> None:
        self._logger = get_logger(f'agent.{self.agent_id}')
    @property
    def agent_id(self) -> str: return type(self).__name__.lower().replace('agent', '')
    @property
    def weight(self) -> float: return self.DEFAULT_WEIGHT
    @abc.abstractmethod
    async def _analyze(self, context: Dict[str, Any]) -> VoteResult: ...
    async def analyze(self, context: Dict[str, Any]) -> VoteResult:
        t0 = time.monotonic()
        try:
            result = await self._analyze(context)
            result.latency_ms = (time.monotonic() - t0) * 1000
            if result.latency_ms > self._SLOW_THRESHOLD_MS:
                self._logger.warning('Slow agent analysis', latency_ms=round(result.latency_ms, 1))
            self._logger.debug('Agent vote', signal=result.signal.value, confidence=round(result.confidence, 3), latency_ms=round(result.latency_ms, 1))
            self._emit_metrics(result)
            return result
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            self._logger.error('Agent error -> ABSTAIN', error=str(exc), latency_ms=round(latency_ms, 1))
            return VoteResult(agent_id=self.agent_id, signal=VoteSignal.ABSTAIN, confidence=0.0, weight=self.weight, latency_ms=latency_ms, reason=f'agent_error: {exc}', error=str(exc))
    def _emit_metrics(self, result: VoteResult) -> None:
        try:
            from ..observability.metrics import metrics_registry
            metrics_registry.increment(f'agent.{self.agent_id}.votes.{result.signal.value.lower()}')
            metrics_registry.histogram(f'agent.{self.agent_id}.latency_ms', result.latency_ms)
        except Exception:  # noqa: C-2 — metrics are optional, never crash agent on metrics failure
            pass
    async def health(self) -> Dict[str, Any]:
        return {'agent_id': self.agent_id, 'weight': self.weight, 'status': 'ok'}
