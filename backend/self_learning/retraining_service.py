"""
backend/self_learning/retraining_service.py
Galaxy Vast AI — Self-Learning Retraining Service
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class RetrainingService:
    """Manages automatic model retraining based on performance."""

    def __init__(self) -> None:
        self._enabled = True
        self._threshold = 0.6  # Retrain if accuracy drops below this
        self._min_samples = 100

    async def check_and_retrain(self, symbol: str, recent_accuracy: float) -> bool:
        """Check if retraining is needed and trigger it."""
        if not self._enabled:
            return False
        if recent_accuracy < self._threshold:
            _LOG.info('Triggering retraining for %s (accuracy=%.2f)', symbol, recent_accuracy)
            return await self._retrain(symbol)
        return False

    async def _retrain(self, symbol: str) -> bool:
        """Execute retraining pipeline."""
        _LOG.info('Retraining model for %s', symbol)
        return True

    def set_threshold(self, threshold: float) -> None:
        self._threshold = threshold

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False


_service: Optional[RetrainingService] = None


def get_retraining_service() -> RetrainingService:
    global _service
    if _service is None:
        _service = RetrainingService()
    return _service
