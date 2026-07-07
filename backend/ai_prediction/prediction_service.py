"""
PredictionService v4 — Phase G Fix

Fixes:
- BUG-G2: asyncio.Lock() at module level → lazy init
- BUG-G4: Uses FeaturePipeline (38 features) not DatasetBuilder.build_single()
- BUG-G5: Saves model with ModelManager versioning after each train
- NEW: prediction_service singleton exported for ContextEnricher
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger("ai_prediction.prediction_service")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass
class PredictionResult:
    """Result from PredictionService.predict()."""

    probability: int
    confidence: int
    risk: RiskLevel
    model_auc: float
    is_tradeable: bool
    reason: str
    is_fallback: bool = field(default=False)

    def to_dict(self) -> dict:
        return {
            "probability": self.probability,
            "confidence": self.confidence,
            "risk": self.risk.value,
            "model_auc": round(self.model_auc, 3),
            "is_tradeable": self.is_tradeable,
            "reason": self.reason,
            "is_fallback": self.is_fallback,
        }


class PredictionService:
    """
    Phase G: wraps ModelManager + FeaturePipeline for real-time predictions.
    Uses 38-feature pipeline (feature_pipeline.py) for consistency with training.
    """

    DEFAULT_MIN_PROBABILITY: int = 60
    DEFAULT_MIN_CONFIDENCE: int = 50

    def __init__(
        self,
        min_probability: int = 60,
        min_confidence: int = 50,
    ) -> None:
        self._min_probability = min_probability
        self._min_confidence = min_confidence
        self._lock: Optional[asyncio.Lock] = None  # BUG-G2 FIX: lazy init
        try:
            from .model_manager import ModelManager

            self._manager = ModelManager()
        except ImportError:
            self._manager = None
            logger.warning("[PredictionService] ModelManager unavailable")

    def _get_lock(self) -> asyncio.Lock:
        """BUG-G2 FIX: lazy init asyncio.Lock inside running event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def predict(self, context: Dict[str, Any]) -> PredictionResult:
        """
        Phase G: predict from enriched context dict.
        context must contain: symbol, direction, confidence, entry,
        smc_analysis, session, etc. (populated by ContextEnricher)
        """
        async with self._get_lock():
            return await self._predict_internal(context)

    async def _predict_internal(self, context: Dict[str, Any]) -> PredictionResult:
        try:
            if self._manager is None:
                return self._neutral_prediction("model manager unavailable", is_fallback=True)

            symbol = context.get("symbol", "default")
            model = self._manager.load_best_model(symbol)
            if model is None:
                return self._neutral_prediction("no trained model available", is_fallback=True)

            meta = self._manager.get_best_metadata(symbol)

            # BUG-G4 FIX: use FeaturePipeline (38 features) for consistency with training
            X = await asyncio.to_thread(self._extract_features, context)

            raw_prob = await asyncio.to_thread(lambda: float(model.predict_proba(X)[0, 1]))
            model_auc = meta.auc_roc if meta else 0.60
            probability = self._calc_probability(raw_prob)
            confluence = float(context.get("smc_confidence", context.get("confidence", 0.5)))
            n_samples = meta.n_samples if meta else 0
            confidence = self._calc_confidence(raw_prob, model_auc, n_samples, confluence)
            risk = self._calc_risk(context, probability)
            is_tradeable = (
                probability >= self._min_probability and confidence >= self._min_confidence
            )
            reason = (
                f"prob={probability}% conf={confidence}% risk={risk.value}"
                if is_tradeable
                else f"below threshold: prob={probability}% conf={confidence}%"
            )
            return PredictionResult(
                probability=probability,
                confidence=confidence,
                risk=risk,
                model_auc=model_auc,
                is_tradeable=is_tradeable,
                reason=reason,
                is_fallback=False,
            )
        except Exception as exc:
            logger.error("[PredictionService] prediction failed: %s", exc, exc_info=True)
            return self._neutral_prediction(f"prediction error: {exc}", is_fallback=True)

    def _extract_features(self, context: Dict[str, Any]) -> np.ndarray:
        """
        BUG-G4 FIX: Extract 38 features from enriched context dict.
        Feature order matches feature_pipeline.get_feature_names().
        """
        try:
            from .feature_pipeline import build_features_from_context

            return build_features_from_context(context)
        except Exception as exc:
            logger.warning("[PredictionService] feature_pipeline failed: %s — using fallback", exc)
            return self._fallback_features(context)

    def _fallback_features(self, context: Dict[str, Any]) -> np.ndarray:
        """12-feature fallback if feature_pipeline unavailable."""
        smc = context.get("smc_analysis", {})
        feats = [
            float(context.get("bos_detected", smc.get("bos_detected", False))),
            float(context.get("choch_detected", smc.get("choch_detected", False))),
            float(context.get("ob_quality", smc.get("ob_quality", 0.0))),
            float(context.get("fvg_size_pips", smc.get("fvg_size_pips", 0.0))),
            float(context.get("liquidity_sweep", smc.get("liquidity_sweep", False))),
            float(context.get("smc_confidence", 0.5)),
            float(context.get("in_kill_zone", False)),
            float(context.get("session_score", 0.5)),
            float(context.get("confidence", 0.5)),
            float(context.get("rr", 1.5)),
            float(context.get("expected_slippage_pips", 0.5)),
            float(str(context.get("direction", "NEUTRAL")) == "BUY"),
        ]
        return np.array([feats], dtype=np.float32)

    def _calc_probability(self, raw_prob: float) -> int:
        return int(round(max(0.0, min(1.0, raw_prob)) * 100))

    def _calc_confidence(
        self, raw_prob: float, model_auc: float, n_samples: int, confluence: float
    ) -> int:
        auc_score = max(0.0, (model_auc - 0.5) * 2.0)
        sample_score = min(1.0, np.log1p(n_samples) / np.log1p(10_000))
        conf_score = max(0.0, min(1.0, confluence))
        return int(round((0.40 * auc_score + 0.30 * sample_score + 0.30 * conf_score) * 100))

    def _calc_risk(self, context: Dict[str, Any], probability: int) -> RiskLevel:
        spread_ratio = float(context.get("spread_ratio", 1.0))
        volatility_high = bool(context.get("volatility_high", False))
        score = 0
        if probability < 65:
            score += 2
        elif probability < 75:
            score += 1
        if spread_ratio > 2.0:
            score += 2
        elif spread_ratio > 1.5:
            score += 1
        if volatility_high:
            score += 1
        if score >= 4:
            return RiskLevel.VERY_HIGH
        if score >= 3:
            return RiskLevel.HIGH
        if score >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _neutral_prediction(self, reason: str, is_fallback: bool = False) -> PredictionResult:
        return PredictionResult(
            probability=50,
            confidence=0,
            risk=RiskLevel.HIGH,
            model_auc=0.0,
            is_tradeable=False,
            reason=reason,
            is_fallback=is_fallback,
        )


# Module-level singleton
_prediction_service: Optional[PredictionService] = None


def get_prediction_service() -> PredictionService:
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService()
    return _prediction_service


prediction_service: PredictionService = get_prediction_service()
