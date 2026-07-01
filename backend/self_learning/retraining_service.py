"""
backend/self_learning/retraining_service.py
Galaxy Vast AI — Self-Learning Retraining Service

Schedules and executes periodic model retraining based on new trade data.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrainingResult:
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    new_version: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


class RetrainingService:
    """Manages periodic ML model retraining."""

    def __init__(self, interval_hours: float = 24.0, min_samples: int = 100) -> None:
        self._interval = interval_hours * 3600
        self._min_samples = min_samples
        self._last_retrain: float = 0.0
        self._history: List[RetrainingResult] = []
        self._log = logging.getLogger(self.__class__.__name__)

    async def should_retrain(self, sample_count: int) -> bool:
        """Check if retraining conditions are met."""
        now = time.time()
        time_ok = (now - self._last_retrain) >= self._interval
        samples_ok = sample_count >= self._min_samples
        return time_ok and samples_ok

    async def retrain(self, data: List[Dict]) -> RetrainingResult:
        """Execute retraining pipeline."""
        started = datetime.now(timezone.utc)
        result = RetrainingResult(started_at=started)
        try:
            self._log.info("Starting retraining with %d samples", len(data))
            # Stub: real implementation calls ML pipeline
            await asyncio.sleep(0.01)  # simulate work
            version = f"v{int(time.time())}"
            result.success = True
            result.new_version = version
            result.metrics = {"accuracy": 0.0, "samples": len(data)}
            result.completed_at = datetime.now(timezone.utc)
            self._last_retrain = time.time()
            self._log.info("Retraining complete: %s", version)
        except Exception as exc:
            result.error = str(exc)
            result.completed_at = datetime.now(timezone.utc)
            self._log.error("Retraining failed: %s", exc)
        self._history.append(result)
        return result

    def history(self, limit: int = 20) -> List[RetrainingResult]:
        return self._history[-limit:]

    @property
    def last_retrain_ts(self) -> float:
        return self._last_retrain


_service: Optional[RetrainingService] = None


def get_retraining_service() -> RetrainingService:
    global _service
    if _service is None:
        _service = RetrainingService()
    return _service
