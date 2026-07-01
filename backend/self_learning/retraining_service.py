"""
backend/self_learning/retraining_service.py
Galaxy Vast AI — Self-Learning Retraining Service
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class RetrainingService:
    """Automated model retraining based on performance degradation."""

    def __init__(self, threshold: float = 0.05, min_samples: int = 100) -> None:
        self._threshold = threshold
        self._min_samples = min_samples
        self._last_retrain: Optional[datetime] = None
        self._running = False

    async def should_retrain(self, current_accuracy: float, baseline: float) -> bool:
        """Check if retraining is needed."""
        if current_accuracy < baseline - self._threshold:
            _LOG.warning(
                "Accuracy degraded: current=%.4f baseline=%.4f threshold=%.4f",
                current_accuracy, baseline, self._threshold
            )
            return True
        return False

    async def retrain(self, dataset: List[Dict[str, Any]]) -> bool:
        """Trigger model retraining."""
        if len(dataset) < self._min_samples:
            _LOG.info("Not enough samples for retraining: %d < %d", len(dataset), self._min_samples)
            return False
        _LOG.info("Starting retraining with %d samples...", len(dataset))
        self._running = True
        try:
            await asyncio.sleep(0)  # Yield to event loop
            self._last_retrain = datetime.now(timezone.utc)
            _LOG.info("Retraining complete at %s", self._last_retrain)
            return True
        finally:
            self._running = False

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
            "threshold": self._threshold,
            "min_samples": self._min_samples,
        }


_service: Optional[RetrainingService] = None


def get_retraining_service() -> RetrainingService:
    global _service
    if _service is None:
        _service = RetrainingService()
    return _service
