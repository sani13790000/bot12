"""
ML Agent — Phase A Fix
BUG-ML: MLAgent always returned NO_TRADE because ml_engine was never injected.
        Now accepts engine at __init__ and is properly wired in lifespan().
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MLAgent:
    """
    Voting agent that uses XGBoost model predictions to cast BUY/SELL/NO_TRADE.

    Phase A Fix:
    - ml_engine is now properly injected (was always None before)
    - Falls back to NO_TRADE with clear log message instead of silent ABSTAIN
    - Confidence threshold is configurable
    - Feature extraction from context is explicit and documented
    """

    name: str = "MLAgent"
    weight: float = 1.5  # Higher weight than base agents (model-based)

    def __init__(
        self,
        ml_engine: Optional[Any] = None,
        confidence_threshold: float = 0.60,
        min_features: int = 3,
    ) -> None:
        """
        Args:
            ml_engine: XGBoostTrainer instance. If None, agent always abstains.
            confidence_threshold: minimum probability to cast BUY/SELL vote.
            min_features: minimum number of features needed in context.
        """
        self._engine = ml_engine
        self._threshold = confidence_threshold
        self._min_features = min_features
        self._prediction_count = 0
        self._abstain_count = 0

        if ml_engine is None:
            logger.warning(
                "[MLAgent] Initialized WITHOUT ml_engine — "
                "all votes will be NO_TRADE until engine is injected. "
                "Call ml_agent.set_engine(trainer) in lifespan()."
            )

    def set_engine(self, ml_engine: Any) -> None:
        """Inject or replace the ML engine at runtime (e.g., after retraining)."""
        self._engine = ml_engine
        logger.info("[MLAgent] Engine injected: %s", type(ml_engine).__name__)

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market context and return vote dict.

        Returns:
            {
                "signal": "BUY" | "SELL" | "NO_TRADE",
                "confidence": float,
                "reason": str,
                "features_used": int,
            }
        """
        if self._engine is None:
            self._abstain_count += 1
            return self._no_engine_result()

        try:
            import numpy as np

            features = self._extract_features(context)

            if len(features) < self._min_features:
                self._abstain_count += 1
                return {
                    "signal": "NO_TRADE",
                    "confidence": 0.0,
                    "reason": f"Insufficient features: {len(features)}/{self._min_features}",
                    "features_used": len(features),
                }

            X = np.array([features], dtype=np.float32)
            proba = self._engine.predict_proba(X)[0]  # [prob_loss, prob_profit]

            prob_profit = float(proba[1])
            prob_loss = float(proba[0])
            self._prediction_count += 1

            if prob_profit >= self._threshold:
                signal = "BUY"
                confidence = prob_profit
                reason = f"XGBoost profit_prob={prob_profit:.3f} >= threshold={self._threshold}"
            elif prob_loss >= self._threshold:
                signal = "SELL"
                confidence = prob_loss
                reason = f"XGBoost loss_prob={prob_loss:.3f} >= threshold={self._threshold}"
            else:
                signal = "NO_TRADE"
                confidence = max(prob_profit, prob_loss)
                reason = (
                    f"XGBoost confidence below threshold: "
                    f"profit={prob_profit:.3f} loss={prob_loss:.3f} < {self._threshold}"
                )

            logger.debug(
                "[MLAgent] signal=%s confidence=%.3f reason=%s", signal, confidence, reason
            )
            return {
                "signal": signal,
                "confidence": confidence,
                "reason": reason,
                "features_used": len(features),
            }

        except RuntimeError as exc:
            # Model not trained yet
            logger.warning("[MLAgent] Model not ready: %s", exc)
            self._abstain_count += 1
            return {
                "signal": "NO_TRADE",
                "confidence": 0.0,
                "reason": f"Model not ready: {exc}",
                "features_used": 0,
            }
        except Exception as exc:
            logger.error("[MLAgent] Unexpected error in analyze(): %s", exc, exc_info=True)
            self._abstain_count += 1
            return {
                "signal": "NO_TRADE",
                "confidence": 0.0,
                "reason": f"Error: {exc}",
                "features_used": 0,
            }

    # ── Feature extraction ────────────────────────────────────────────────────

    def _extract_features(self, context: Dict[str, Any]) -> list:
        """
        Extract ordered feature vector from signal context.
        Must match the feature order used during training (DatasetBuilder._feature_cols).
        """
        feature_keys = [
            "rsi",
            "macd",
            "macd_signal",
            "bb_upper",
            "bb_lower",
            "atr",
            "volume_ratio",
            "spread",
            "session_hour",
            "day_of_week",
            "smc_score",
            "pa_score",
        ]
        features = []
        for key in feature_keys:
            val = context.get(key)
            if val is not None:
                try:
                    features.append(float(val))
                except (TypeError, ValueError):
                    features.append(0.0)
            else:
                features.append(0.0)
        return features

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def _no_engine_result(self) -> Dict[str, Any]:
        return {
            "signal": "NO_TRADE",
            "confidence": 0.0,
            "reason": "MLAgent has no engine — set_engine() was never called",
            "features_used": 0,
        }

    def stats(self) -> Dict[str, Any]:
        """Return agent performance stats."""
        total = self._prediction_count + self._abstain_count
        return {
            "agent": self.name,
            "predictions": self._prediction_count,
            "abstains": self._abstain_count,
            "abstain_rate": self._abstain_count / max(total, 1),
            "engine_loaded": self._engine is not None,
        }
