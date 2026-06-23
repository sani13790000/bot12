"""backend/ai_prediction/prediction_service.py v3 — Phase T"""
from __future__ import annotations
import asyncio, logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np

logger = logging.getLogger("ai_prediction.prediction_service")
_PREDICT_LOCK = asyncio.Lock()


class RiskLevel(str, Enum):
    LOW       = "LOW"
    MEDIUM    = "MEDIUM"
    HIGH      = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass
class PredictionResult:
    """T-4: is_fallback field added."""
    probability:  int
    confidence:   int
    risk:         RiskLevel
    model_auc:    float
    is_tradeable: bool
    reason:       str
    is_fallback:  bool = field(default=False)  # T-4

    def to_dict(self) -> dict:
        return {"probability": self.probability, "confidence": self.confidence,
                "risk": self.risk.value, "model_auc": round(self.model_auc, 3),
                "is_tradeable": self.is_tradeable, "reason": self.reason,
                "is_fallback": self.is_fallback}


class PredictionService:
    DEFAULT_MIN_PROBABILITY: int = 60
    DEFAULT_MIN_CONFIDENCE:  int = 50

    def __init__(self, min_probability: int = 60, min_confidence: int = 50) -> None:
        try:
            from .model_manager import ModelManager
            from .dataset_builder import DatasetBuilder
            self._manager = ModelManager()
            self._builder = DatasetBuilder()
        except ImportError:
            self._manager = None
            self._builder = None
        self._min_probability = min_probability
        self._min_confidence  = min_confidence

    async def predict(self, signal) -> PredictionResult:  # T-1: async
        async with _PREDICT_LOCK:  # T-3
            return await self._predict_internal(signal)

    async def _predict_internal(self, signal) -> PredictionResult:
        try:
            model = self._manager.load_best_model(signal.symbol)
            if model is None:
                logger.warning("no trained model for %s", signal.symbol)
                return self._neutral_prediction("no trained model available")
            X        = self._builder.build_single(signal)
            meta     = self._manager.get_best_metadata(signal.symbol)
            raw_prob = await asyncio.to_thread(  # T-1: non-blocking
                lambda: float(model.predict_proba(X)[0, 1])
            )
            model_auc   = meta.auc_roc if meta else 0.60
            probability = self._calc_probability(raw_prob)
            confidence  = self._calc_confidence(
                raw_prob, model_auc,
                meta.n_samples if meta else 0,
                signal.decision_score / 100.0,
            )
            risk = self._calc_risk(signal, probability)  # T-5: was missing
            is_tradeable = (  # T-6: thresholds enforced
                probability >= self._min_probability
                and confidence >= self._min_confidence
            )
            reason = (
                f"prob={probability}% conf={confidence}% risk={risk.value}"
                if is_tradeable
                else f"below threshold: prob={probability}% conf={confidence}%"
            )
            return PredictionResult(  # T-2: return was missing!
                probability=probability, confidence=confidence, risk=risk,
                model_auc=model_auc, is_tradeable=is_tradeable,
                reason=reason, is_fallback=False,
            )
        except Exception as exc:
            logger.error("prediction failed for %s: %s",
                         getattr(signal, "symbol", "?"), exc, exc_info=True)
            return self._neutral_prediction(f"prediction error: {exc}", is_fallback=True)

    def _calc_probability(self, raw_prob: float) -> int:
        return int(round(max(0.0, min(1.0, raw_prob)) * 100))

    def _calc_confidence(self, raw_prob, model_auc, n_samples, confluence) -> int:
        auc_score    = max(0.0, (model_auc - 0.5) * 2.0)
        sample_score = min(1.0, np.log1p(n_samples) / np.log1p(10_000))
        conf_score   = max(0.0, min(1.0, confluence))
        return int(round((0.40 * auc_score + 0.30 * sample_score + 0.30 * conf_score) * 100))

    def _calc_risk(self, signal, probability: int) -> RiskLevel:  # T-5
        spread_ratio    = getattr(signal, "spread_ratio",    1.0)
        volatility_high = getattr(signal, "volatility_high", False)
        score = 0
        if probability  < 65:    score += 2
        elif probability < 75:   score += 1
        if spread_ratio  > 2.0:  score += 2
        elif spread_ratio > 1.5: score += 1
        if volatility_high:      score += 1
        if score >= 4: return RiskLevel.VERY_HIGH
        if score >= 3: return RiskLevel.HIGH
        if score >= 1: return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _neutral_prediction(self, reason: str, is_fallback: bool = False) -> PredictionResult:
        return PredictionResult(probability=50, confidence=0, risk=RiskLevel.HIGH,
                                model_auc=0.0, is_tradeable=False,
                                reason=reason, is_fallback=is_fallback)
