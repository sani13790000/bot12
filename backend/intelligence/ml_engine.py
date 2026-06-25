"""ML Engine — Phase 5: Walk-Forward CV, Concept Drift Detection, Feature Importance.

Fixes:
  - ML-Ex-1: Walk-forward embargo prevents leakage
  - ML-Ex-2: Concurrent training guard via asyncio.Lock
  - LOG-FIX-1: ConceptDriftDetector._history �-bounded deque(maxlen=1000)
  - LOG-FIX-2: _get_feature_importance except Exception ⁵ AttributeError + log
"""
from __future__ import annotations
from collections import deque
import asyncio, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

from ..core.logger import get_logger

logger = get_logger("intelligence.ml_engine")


class DriftStatus(Enum):
    STABLE = "stable"
    WARNING = "warning"
    DRIFTED = "drifted"


class MLPrediction:
    def __init__(self, direction: str, confidence: float,
                 risk: float = 0.5, importance: Optional[Dict[str, float]] = None):
        self.direction = direction
        self.confidence = confidence
        self.risk = risk
        self.importance = importance or {}


class ConceptDriftDetector:
    """Page-Hinkley drift detection."""
    def __init__(self, delta: float = 0.005, threshold: float = 50.0, alpha: float = 0.9999):
        self.delta = delta
        self.threshold = threshold
        self.alpha = alpha
        self._cum_sum = 0.0
        self._min_sum = 0.0
        self._mean = 0.0
        self._n = 0
        self._history: deque = deque(maxlen=1000)  # LOG-FIX-1: bounded — prevents memory leak after 1000+ predictions

    def update(self, value: float) -> DriftStatus:
        self._n += 1
        self._history.append(value)
        if self._n == 1:
            self._mean = value
        else:
            self._mean = self.alpha * self._mean + (1 - self.alpha) * value
        self._cum_sum += value - self._mean - self.delta
        self._min_sum = min(self._min_sum, self._cum_sum)
        ph_stat = self._cum_sum - self._min_sum
        if ph_stat > self.threshold:
            self.reset()
            return DriftStatus.DRIFTED
        if ph_stat > self.threshold * 0.5:
            return DriftStatus.WARNING
        return DriftStatus.STABLE

    def reset(self) -> None:
        self._cum_sum = 0.0
        self._min_sum = 0.0

    def drift_score(self) -> float:
        return max(0.0, self._cum_sum - self._min_sum) / max(self.threshold, 1.0)

    def recent_mean(self, window: int = 20) -> float:
        if not self._history:
            return 0.0
        tail = list(self._history)[-window:]
        return sum(tail) / len(tail)
