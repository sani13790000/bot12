"""Retraining Service — Phase F fix.

Fixes BUG-F4: import path was `backend.intelligence.xgboost_trainer`
(module does NOT exist) — corrected to `backend.ai_prediction.xgboost_trainer`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# BUG-F4 FIX: correct import path
from backend.ai_prediction.xgboost_trainer import XGBoostTrainer  # noqa: E402

_RETRAIN_INTERVAL_SECONDS = 6 * 60 * 60   # 6 hours
_MIN_SAMPLES_TO_RETRAIN   = 50
_MIN_ACCURACY_IMPROVEMENT = 0.01          # 1% improvement threshold


class RetrainingService:
    """Background service that periodically retrains the XGBoost model."""

    def __init__(self, trainer: Optional[XGBoostTrainer] = None) -> None:
        self._trainer: Optional[XGBoostTrainer] = trainer or XGBoostTrainer()
        self._task:    Optional[asyncio.Task]    = None
        self._running: bool                      = False
        self._last_run: Optional[datetime]       = None
        self._last_metrics: Dict[str, Any]       = {}
        logger.info("[RetrainingService] initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_trainer(self, trainer: XGBoostTrainer) -> None:
        self._trainer = trainer
        logger.info("[RetrainingService] trainer set: %s", type(trainer).__name__)

    async def start(self) -> None:
        """Start background retraining loop."""
        if self._running:
            logger.warning("[RetrainingService] already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="retraining_loop")
        logger.info(
            "[RetrainingService] started — interval=%ds", _RETRAIN_INTERVAL_SECONDS
        )

    async def stop(self) -> None:
        """Stop background loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[RetrainingService] stopped")

    async def retrain_now(self) -> Dict[str, Any]:
        """Trigger an immediate retraining cycle and return metrics."""
        return await self._retrain()

    def status(self) -> Dict[str, Any]:
        return {
            "running":      self._running,
            "last_run":     self._last_run.isoformat() if self._last_run else None,
            "last_metrics": self._last_metrics,
            "trainer_ok":   self._trainer is not None,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Background loop: wait interval then retrain."""
        # Initial delay: 5 minutes after startup to let system warm up
        await asyncio.sleep(5 * 60)
        while self._running:
            try:
                await self._retrain()
            except Exception as exc:
                logger.error("[RetrainingService] loop error: %s", exc, exc_info=True)
            await asyncio.sleep(_RETRAIN_INTERVAL_SECONDS)

    async def _retrain(self) -> Dict[str, Any]:
        """Run one retraining cycle in a thread pool."""
        if self._trainer is None:
            logger.error("[RetrainingService] no trainer — skipping")
            return {"error": "no trainer"}

        logger.info("[RetrainingService] starting retraining cycle")
        start_ts = datetime.now(timezone.utc)

        try:
            # train_latest() reads from DB, trains, saves model
            loop    = asyncio.get_running_loop()     # Python 3.10+ safe
            metrics = await loop.run_in_executor(
                None, self._trainer.train_latest
            )

            if metrics is None:
                metrics = {}

            elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
            new_acc = float(metrics.get("accuracy", 0.0))
            old_acc = float(self._last_metrics.get("accuracy", 0.0))
            improved = new_acc >= old_acc + _MIN_ACCURACY_IMPROVEMENT

            result = {
                "success":   True,
                "elapsed_s": round(elapsed, 1),
                "improved":  improved,
                "new_acc":   round(new_acc, 4),
                "old_acc":   round(old_acc, 4),
                "metrics":   metrics,
                "timestamp": start_ts.isoformat(),
            }

            self._last_run     = datetime.now(timezone.utc)
            self._last_metrics = metrics

            logger.info(
                "[RetrainingService] done: acc=%.4f improved=%s elapsed=%.1fs",
                new_acc, improved, elapsed,
            )
            return result

        except Exception as exc:
            logger.error(
                "[RetrainingService] retraining failed: %s", exc, exc_info=True
            )
            return {
                "success":  False,
                "error":    str(exc),
                "timestamp": start_ts.isoformat(),
            }


# Module-level singleton
_service: Optional[RetrainingService] = None


def get_retraining_service() -> RetrainingService:
    global _service
    if _service is None:
        _service = RetrainingService()
    return _service


retraining_service: RetrainingService = get_retraining_service()
