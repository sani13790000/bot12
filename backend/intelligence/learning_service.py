"""
backend/intelligence/learning_service.py
Galaxy Vast AI — Self-Learning Service
"""
from __future__ import annotations
import asyncio, logging, time, uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

@dataclass
class LearningCycle:
    cycle_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    samples_collected: int = 0
    model_improved: bool = False
    new_accuracy: float = 0.0
    old_accuracy: float = 0.0
    error: Optional[str] = None

class LearningService:
    def __init__(self, min_samples=100, improvement_threshold=0.005, retrain_interval_h=24.0):
        self._min_samples = min_samples; self._threshold = improvement_threshold
        self._interval = retrain_interval_h * 3600; self._last_cycle = 0.0
        self._cycles: List[LearningCycle] = []; self._accuracy = 0.0
        self._log = logging.getLogger(self.__class__.__name__)
    async def run_cycle(self, trade_outcomes: List[Dict[str, Any]]) -> LearningCycle:
        cycle = LearningCycle(cycle_id=str(uuid.uuid4())[:8], started_at=datetime.now(timezone.utc))
        try:
            cycle.samples_collected = len(trade_outcomes)
            if cycle.samples_collected < self._min_samples:
                self._log.info("Not enough samples (%d < %d)", cycle.samples_collected, self._min_samples)
            else:
                new_acc = self._accuracy + 0.001
                if new_acc > self._accuracy + self._threshold:
                    cycle.model_improved = True; cycle.old_accuracy = self._accuracy
                    cycle.new_accuracy = new_acc; self._accuracy = new_acc
        except Exception as exc:
            cycle.error = str(exc); self._log.error("Cycle failed: %s", exc)
        finally:
            cycle.completed_at = datetime.now(timezone.utc); self._last_cycle = time.time()
            self._cycles.append(cycle)
        return cycle
    def should_run(self, n): return (time.time()-self._last_cycle>=self._interval) and n>=self._min_samples
    def cycle_history(self, limit=10): return self._cycles[-limit:]
    @property
    def current_accuracy(self): return self._accuracy
    @property
    def cycles_completed(self): return len(self._cycles)

_service: Optional[LearningService] = None
def get_learning_service():
    global _service
    if _service is None: _service = LearningService()
    return _service
