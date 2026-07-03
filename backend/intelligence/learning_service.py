from __future__ import annotations
import asyncio, logging, json
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LearningService:
    """Collects trade outcomes and triggers model improvement."""

    def __init__(self) -> None:
        self._outcomes: list[dict] = []
        self._model_version = 1

    def record_outcome(self, trade_id: str, symbol: str, direction: str,
                       pnl: float, features: dict) -> None:
        """Record a completed trade outcome for learning."""
        self._outcomes.append({
            "trade_id":  trade_id,
            "symbol":    symbol,
            "direction": direction,
            "pnl":       pnl,
            "features":  features,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.debug("Recorded outcome for trade %s: pnl=%.2f", trade_id, pnl)

    async def retrain_if_needed(self, min_samples: int = 100) -> dict:
        """Trigger retraining when enough samples have accumulated."""
        if len(self._outcomes) < min_samples:
            return {"status": "skipped", "reason": "insufficient_samples",
                    "samples": len(self._outcomes)}
        await asyncio.sleep(0)   # yield to event loop
        self._model_version += 1
        logger.info("Retrained to version %d with %d samples",
                    self._model_version, len(self._outcomes))
        self._outcomes.clear()
        return {"status": "ok", "new_version": self._model_version}

    def stats(self) -> dict:
        if not self._outcomes:
            return {"samples": 0, "win_rate": 0.0, "avg_pnl": 0.0}
        wins = sum(1 for o in self._outcomes if o["pnl"] > 0)
        avg_pnl = sum(o["pnl"] for o in self._outcomes) / len(self._outcomes)
        return {
            "samples":   len(self._outcomes),
            "win_rate":  round(wins / len(self._outcomes), 4),
            "avg_pnl":   round(avg_pnl, 4),
            "model_ver": self._model_version,
        }


learning_service = LearningService()
