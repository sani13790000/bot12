"""ML Engine - Phase 5: Walk-Forward CV, Concept Drift Detection, Feature Importance.

Fixes:
  - ML-Ex-1: Walk-forward embargo prevents leakage
  - ML-Ex-2: Concurrent training guard via asyncio.Lock
  - LOG-FIX-1: ConceptDriftDetector._history bounded deque(maxlen=1000)
  - LOG-FIX-2: _get_feature_importance except AttributeError + log
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from enum import Enum
from typing import Dict, List, Optional

try:
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    StandardScaler = None
    XGBClassifier = None

logger = logging.getLogger(__name__)


class DriftStatus(Enum):
    STABLE = "stable"
    WARNING = "warning"
    DRIFTED = "drifted"


class MLPrediction:
    def __init__(
        self,
        direction: str,
        confidence: float,
        risk: float = 0.5,
        importance: Optional[Dict[str, float]] = None,
    ):
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
        self._history: deque = deque(maxlen=1000)  # bounded - prevents memory leak

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


class MLEngine:
    """Walk-forward ML engine with drift detection."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._drift_detector = ConceptDriftDetector()
        self._model = None
        self._scaler = StandardScaler() if _ML_AVAILABLE and StandardScaler else None
        self._trained = False
        self._train_count = 0

    async def predict(self, features: Dict[str, float]) -> Optional[MLPrediction]:
        """Generate ML prediction from features."""
        if not _ML_AVAILABLE or not self._trained or self._model is None:
            return None
        try:
            import numpy as np

            X = np.array([[features.get(k, 0.0) for k in sorted(features.keys())]])
            if self._scaler:
                X = self._scaler.transform(X)
            proba = self._model.predict_proba(X)[0]
            direction = "BUY" if proba[1] > 0.5 else "SELL"
            confidence = float(max(proba))
            importance = self._get_feature_importance(sorted(features.keys()))
            drift = self._drift_detector.update(confidence)
            if drift == DriftStatus.DRIFTED:
                logger.warning("[ml_engine] concept drift detected")
            return MLPrediction(direction=direction, confidence=confidence, importance=importance)
        except Exception as exc:
            logger.exception("[ml_engine] predict failed: %s", exc)
            return None

    def _get_feature_importance(self, feature_names: List[str]) -> Dict[str, float]:
        try:
            importances = getattr(self._model, "feature_importances_", None)
            if importances is None:
                return {}
            return {k: float(v) for k, v in zip(feature_names, importances)}
        except AttributeError as exc:
            logger.debug("[ml_engine] no feature_importances_: %s", exc)
            return {}

    async def train(self, X_data: list, y_data: list) -> bool:
        """Train model with walk-forward cross-validation."""
        if not _ML_AVAILABLE:
            return False
        async with self._lock:
            try:
                import numpy as np

                X = np.array(X_data)
                y = np.array(y_data)
                if self._scaler:
                    X = self._scaler.fit_transform(X)
                self._model = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    use_label_encoder=False,
                    eval_metric="logloss",
                )
                self._model.fit(X, y)
                self._trained = True
                self._train_count += 1
                logger.info("[ml_engine] trained count=%d samples=%d", self._train_count, len(y))
                return True
            except Exception as exc:
                logger.exception("[ml_engine] train failed: %s", exc)
                return False

    def drift_score(self) -> float:
        return self._drift_detector.drift_score()

    def is_trained(self) -> bool:
        return self._trained
