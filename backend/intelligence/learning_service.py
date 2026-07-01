"""
backend/intelligence/learning_service.py
Galaxy Vast AI — Learning Service

Orchestrates the self-learning pipeline:
  1. Collect completed trade outcomes
  2. Extract features from historical data
  3. Trigger model retraining when conditions met
  4. Validate new model against holdout
  5. Promote if better than baseline
  6. Adjust agent weights based on performance
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
class LearningCycle:
    cycle_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    samples_collected: int = 0
    features_extracted: int = 0
    model_improved: bool = False
    new_accuracy: float = 0.0
    old_accuracy: float = 0.0
    weights_updated: bool = False
    error: Optional[str] = None


class LearningService:
    """Manages the continuous self-improvement loop."""

    def __init__(
        self,
        min_samples: int = 100,
        improvement_threshold: float = 0.005,
        retrain_interval_h: float = 24.0,
    ) -> None:
        self._min_samples = min_samples
        self._threshold = improvement_threshold
        self._interval = retrain_interval_h * 3600
        self._last_cycle: float = 0.0
        self._cycles: List[LearningCycle] = []
        self._current_accuracy: float = 0.0
        self._log = logging.getLogger(self.__class__.__name__)

    async def run_cycle(self, trade_outcomes: List[Dict[str, Any]]) -> LearningCycle:
        """Execute one learning cycle."""
        import uuid
        cycle = LearningCycle(
            cycle_id=str(uuid.uuid4())[:8],
            started_at=datetime.now(timezone.utc),
        )
        try:
            cycle.samples_collected = len(trade_outcomes)
            if cycle.samples_collected < self._min_samples:
                self._log.info("Not enough samples (%d < %d)", cycle.samples_collected, self._min_samples)
                cycle.completed_at = datetime.now(timezone.utc)
                return cycle

            # Feature extraction
            features = await self._extract_features(trade_outcomes)
            cycle.features_extracted = len(features)

            # Retraining (stub - calls actual trainer in production)
            new_accuracy = await self._retrain(features)

            if new_accuracy > self._current_accuracy + self._threshold:
                cycle.model_improved = True
                cycle.old_accuracy = self._current_accuracy
                cycle.new_accuracy = new_accuracy
                self._current_accuracy = new_accuracy
                # Update agent weights
                await self._update_weights(new_accuracy)
                cycle.weights_updated = True
                self._log.info("Model improved: %.4f -> %.4f", cycle.old_accuracy, new_accuracy)
            else:
                cycle.new_accuracy = new_accuracy
                cycle.old_accuracy = self._current_accuracy
                self._log.info("No improvement: new=%.4f baseline=%.4f", new_accuracy, self._current_accuracy)

        except Exception as exc:
            cycle.error = str(exc)
            self._log.error("Learning cycle failed: %s", exc)
        finally:
            cycle.completed_at = datetime.now(timezone.utc)
            self._last_cycle = time.time()
            self._cycles.append(cycle)
        return cycle

    async def _extract_features(self, outcomes: List[Dict]) -> List[Dict]:
        """Extract ML features from trade outcomes."""
        await asyncio.sleep(0)  # yield
        features = []
        for o in outcomes:
            f = {
                "symbol": o.get("symbol", ""),
                "direction": 1 if o.get("direction") == "BUY" else -1,
                "confidence": o.get("confidence", 0.5),
                "lot_size": o.get("lot_size", 0.01),
                "profit_pips": o.get("profit_pips", 0.0),
                "duration_min": o.get("duration_min", 0.0),
                "label": 1 if o.get("profitable", False) else 0,
            }
            features.append(f)
        return features

    async def _retrain(self, features: List[Dict]) -> float:
        """Retrain model. Returns new accuracy. Stub."""
        await asyncio.sleep(0.01)
        return self._current_accuracy + 0.001

    async def _update_weights(self, accuracy: float) -> None:
        """Update agent decision weights based on performance."""
        await asyncio.sleep(0)

    def should_run(self, sample_count: int) -> bool:
        now = time.time()
        return (now - self._last_cycle >= self._interval) and (sample_count >= self._min_samples)

    def cycle_history(self, limit: int = 10) -> List[LearningCycle]:
        return self._cycles[-limit:]

    @property
    def current_accuracy(self) -> float:
        return self._current_accuracy

    @property
    def cycles_completed(self) -> int:
        return len(self._cycles)


_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _service
    if _service is None:
        _service = LearningService()
    return _service
