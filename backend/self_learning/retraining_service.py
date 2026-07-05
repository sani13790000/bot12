"""
Retraining Service — Phase G Fix
Fixes:
- BUG-G9: import path was backend.intelligence.xgboost_trainer (non-existent)
          → backend.ai_prediction.xgboost_trainer (correct)
- ARCH: set_trainer() method added so main.py lifespan can inject trainer
- ARCH: start()/stop() lifecycle management
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RetrainingService:
    """
    Periodic ML model retraining.
    Interval: every RETRAIN_INTERVAL_HOURS (default 6h).
    On startup, loads existing model first.
    """

    def __init__(self, interval_hours: float = 6.0) -> None:
        self._interval_hours = interval_hours
        self._trainer: Optional[Any] = None
        self._task:    Optional[asyncio.Task] = None
        self._running: bool = False
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[Any] = None

    def set_trainer(self, trainer: Any) -> None:
        """Inject XGBoostTrainer instance (called from main.py lifespan)."""
        self._trainer = trainer
        logger.info("[RetrainingService] trainer set: %s", type(trainer).__name__)

    async def start(self) -> None:
        """Start background retraining loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="retraining_loop")
        logger.info(
            "[RetrainingService] started — interval=%.1fh", self._interval_hours
        )

    async def stop(self) -> None:
        """Stop background retraining loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[RetrainingService] stopped")

    async def _loop(self) -> None:
        """Background loop: sleep → retrain → repeat."""
        # First retrain after a short delay (let system warm up)
        await asyncio.sleep(60)
        while self._running:
            try:
                await self._retrain()
            except Exception as exc:
                logger.error("[RetrainingService] retrain error: %s", exc, exc_info=True)
            await asyncio.sleep(self._interval_hours * 3600)

    async def _retrain(self) -> None:
        """Execute one retraining cycle."""
        if self._trainer is None:
            # BUG-G9 FIX: correct import path
            try:
                from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
                self._trainer = XGBoostTrainer()
                logger.info("[RetrainingService] auto-created XGBoostTrainer")
            except ImportError as exc:
                logger.error(
                    "[RetrainingService] cannot import XGBoostTrainer — "
                    "check backend.ai_prediction.xgboost_trainer exists: %s", exc
                )
                return

        logger.info("[RetrainingService] starting retrain cycle")
        start_ts = datetime.now(timezone.utc)

        result = await self._trainer.train_latest()

        self._last_run    = start_ts
        self._last_result = result

        logger.info(
            "[RetrainingService] retrain complete — acc=%.4f f1=%.4f n=%d path=%s",
            result.accuracy,
            result.f1,
            result.n_samples,
            result.model_path or "(not saved)",
        )

    def stats(self) -> dict:
        """Return service statistics for health endpoint."""
        return {
            "running":      self._running,
            "interval_h":  self._interval_hours,
            "last_run":     self._last_run.isoformat() if self._last_run else None,
            "last_accuracy": round(self._last_result.accuracy, 4) if self._last_result else None,
            "last_f1":       round(self._last_result.f1, 4)       if self._last_result else None,
        }


# Module-level singleton
retraining_service: RetrainingService = RetrainingService()
