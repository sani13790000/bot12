"""Retraining Service -- Phase P Fix P-5a/b/c/d."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def _utcnow() -> datetime:
    """FIX P-5a: timezone-aware UTC. Never use datetime.utcnow()."""
    return datetime.now(timezone.utc)

class RetrainingService:
    MIN_SAMPLES = 50
    RETRAIN_INTERVAL_HOURS = 24
    DRIFT_THRESHOLD = 0.5
    OVERFIT_THRESHOLD = 1.3

    def __init__(self, trade_memory=None, ml_engine=None, model_manager=None, db=None):
        self._memory = trade_memory
        self._engine = ml_engine
        self._manager = model_manager
        self._db = db
        self._last_retrain: Optional[datetime] = None
        self._retrain_count = 0
        self._running = False

    async def run_forever(self, interval_hours: float = 6.0) -> None:
        self._running = True
        logger.info("[RetrainingService] started, interval=%.1fh", interval_hours)
        while self._running:
            try:
                await self.check_and_retrain()
            except Exception as exc:
                logger.error("[RetrainingService] loop error: %s", exc)
            await asyncio.sleep(interval_hours * 3600)

    def stop(self) -> None:
        self._running = False

    async def check_and_retrain(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "checked_at": _utcnow().isoformat(),
            "retrained": False,
            "reason": None,
            "training_result": None,
        }
        try:
            samples = await self._get_sample_count()
            if samples < self.MIN_SAMPLES:
                result["reason"] = f"insufficient_samples:{samples}<{self.MIN_SAMPLES}"
                return result
            needs_retrain, reason = await self._should_retrain()
            if not needs_retrain:
                result["reason"] = reason
                return result
            training_result = await asyncio.to_thread(self._run_training_sync)
            result["retrained"] = True
            result["reason"] = reason
            result["training_result"] = training_result
            self._last_retrain = _utcnow()
            self._retrain_count += 1
            logger.info("[RetrainingService] retrain #%d complete", self._retrain_count)
        except Exception as exc:
            logger.error("[RetrainingService] error: %s", exc)
            result["error"] = str(exc)
        return result

    async def _should_retrain(self):
        if self._last_retrain is None:
            return True, "first_run"
        age = (_utcnow() - self._last_retrain).total_seconds() / 3600
        if age >= self.RETRAIN_INTERVAL_HOURS:
            return True, f"stale:{age:.1f}h"
        drift = await self._compute_drift_score()
        if drift >= self.DRIFT_THRESHOLD:
            return True, f"drift:{drift:.3f}"
        return False, f"healthy:age={age:.1f}h"

    async def _compute_drift_score(self) -> float:
        if self._engine is None:
            return 0.0
        try:
            stats = await asyncio.to_thread(self._engine.get_drift_stats)
            return float(stats.get("drift_score", 0.0))
        except Exception as exc:
            logger.warning("[RetrainingService] drift failed: %s", exc)
            return 0.0

    async def _get_sample_count(self) -> int:
        if self._memory is None:
            return 0
        try:
            trades = await asyncio.to_thread(self._memory.get_recent_trades, 1000)
            return len(trades) if trades else 0
        except Exception:
            return 0

    def _run_training_sync(self) -> Dict[str, Any]:
        if self._engine is None:
            return {"skipped": "no_engine"}
        try:
            trades = self._memory.get_recent_trades(500) if self._memory else []
            if not trades:
                return {"skipped": "no_data"}
            result = self._engine.train(trades)
            train_acc = float(getattr(result, "train_accuracy", 0.0) or 0.0)
            test_acc  = float(getattr(result, "test_accuracy",  0.0) or 0.0)
            overfit_ratio = train_acc / test_acc if test_acc > 0.01 else 0.0
            if overfit_ratio > self.OVERFIT_THRESHOLD:
                logger.warning("[RetrainingService] overfit ratio=%.2f", overfit_ratio)
            if self._manager and getattr(result, "model", None):
                self._manager.save(result.model)
            return {
                "train_accuracy": round(train_acc, 4),
                "test_accuracy":  round(test_acc,  4),
                "overfit_ratio":  round(overfit_ratio, 4),
                "trained_at":     _utcnow().isoformat(),
            }
        except Exception as exc:
            logger.error("[RetrainingService] training failed: %s", exc)
            return {"error": str(exc)}

    async def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "retrain_count": self._retrain_count,
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
            "drift_threshold": self.DRIFT_THRESHOLD,
            "min_samples": self.MIN_SAMPLES,
        }
