"""ML Agent — Phase 5: uses UnifiedMLEngine, returns drift info, feature importance."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MLAgent:
    """Agent that queries the ML engine and returns a structured vote result."""

    name = "ml_agent"
    weight = 1.0

    def __init__(self, ml_engine: Optional[Any] = None):
        self._engine = ml_engine
        self._prediction_count = 0

    # ------------------------------------------------------------------ #
    #  MAIN ENTRY POINT (called by VotingEngine)
    # ------------------------------------------------------------------ #

    async def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Return agent result compatible with VotingEngine."""
        if self._engine is None:
            return self._no_engine_result()

        try:
            features = self._extract_features(market_data)
            prediction = self._engine.predict(features)
            self._prediction_count += 1

            direction = getattr(prediction, "direction", "NO_TRADE")
            confidence = float(getattr(prediction, "confidence", 0.5))
            risk_score = float(getattr(prediction, "risk_score", 0.5))
            should_trade = bool(getattr(prediction, "should_trade", False))
            reliability = float(getattr(prediction, "reliability_score", confidence))
            importance = getattr(prediction, "feature_importance", {})
            version = getattr(prediction, "model_version", "1.0")

            # Convert to VotingEngine-compatible score (0–100)
            score = round(reliability * 100, 2) if should_trade else 50.0

            drift_info = {}
            if hasattr(self._engine, "get_drift_info"):
                try:
                    drift_info = self._engine.get_drift_info()
                except Exception:
                    pass

            return {
                "agent": self.name,
                "direction": direction,
                "score": score,
                "confidence": confidence,
                "risk_score": risk_score,
                "should_trade": should_trade,
                "reliability": reliability,
                "feature_importance": importance,
                "model_version": version,
                "drift_info": drift_info,
                "prediction_count": self._prediction_count,
                "error": None,
            }

        except Exception as exc:
            logger.error("[MLAgent] analyze error: %s", exc)
            return {
                "agent": self.name,
                "direction": "NO_TRADE",
                "score": 50.0,
                "confidence": 0.5,
                "risk_score": 0.5,
                "should_trade": False,
                "error": str(exc),
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "engine_available": self._engine is not None,
            "engine_trained": getattr(self._engine, "is_trained", False) if self._engine else False,
            "engine_version": getattr(self._engine, "model_version", None) if self._engine else None,
            "prediction_count": self._prediction_count,
        }

    # ------------------------------------------------------------------ #
    #  FEATURE EXTRACTION
    # ------------------------------------------------------------------ #

    def _extract_features(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract the 15-feature vector MLEngine expects from market_data context."""
        smc = market_data.get("smc") or {}
        pa = market_data.get("price_action") or {}
        session = str(market_data.get("session") or "").upper()
        risk = market_data.get("risk") or {}

        return {
            "pnl_pips": float(market_data.get("last_pnl_pips", 0) or 0),
            "realized_rr": float(market_data.get("last_rr", 0) or 0),
            "confidence_score": float(market_data.get("confidence", 50) or 50) / 100.0,
            "duration_minutes": float(market_data.get("avg_duration_minutes", 0) or 0),
            "previous_consecutive_losses": float(market_data.get("consecutive_losses", 0) or 0),
            "news_active": 1.0 if market_data.get("news_active") else 0.0,
            "smc_ob_count": float(smc.get("order_blocks", 0) or 0),
            "smc_fvg_count": float(smc.get("fvg_count", 0) or 0),
            "smc_liquidity": float(smc.get("liquidity_score", 0) or 0),
            "pa_pin_bar": 1.0 if pa.get("pin_bar") else 0.0,
            "pa_engulfing": 1.0 if pa.get("engulfing") else 0.0,
            "pa_inside_bar": 1.0 if pa.get("inside_bar") else 0.0,
            "session_asian": 1.0 if "ASIAN" in session else 0.0,
            "session_london": 1.0 if "LONDON" in session else 0.0,
            "session_ny": 1.0 if "NEW_YORK" in session or "NY" in session else 0.0,
        }

    def _no_engine_result(self) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "direction": "NO_TRADE",
            "score": 50.0,
            "confidence": 0.5,
            "risk_score": 0.5,
            "should_trade": False,
            "error": "ml_engine_not_initialized",
        }
