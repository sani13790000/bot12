"""
backend/self_learning/retraining_service.py
Galaxy Vast AI - ML Model Retraining Service

BUG-7 FIX: _retrain() was hardcoding new_acc = 0.80 with a TODO comment.
Now calls XGBoostTrainer.train_latest() via run_in_executor for real training.

Triggers model retraining when:
- Enough new labelled trades are available
- Win-rate drops below threshold
- A manual trigger is issued
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_MIN_SAMPLES   = 100    # minimum new samples before retraining
_WINRATE_FLOOR = 0.45   # retrain if win-rate drops below 45%


@dataclass
class RetrainingResult:
    """Result of a retraining run."""
    triggered:         bool
    trigger_reason:    str
    samples_used:      int
    old_accuracy:      float
    new_accuracy:      float
    improvement:       float
    duration_s:        float
    completed_at:      str


class RetrainingService:
    """
    Decides when to retrain and orchestrates the process.
    """

    def __init__(
        self,
        model_manager: Any = None,
        trade_store:   Any = None,
    ) -> None:
        self._mm    = model_manager
        self._ts    = trade_store
        self._last_retrain: Optional[str] = None

    async def check_and_retrain(self) -> Optional[RetrainingResult]:
        """
        Check conditions and retrain if needed.
        Returns RetrainingResult if retrained, else None.
        """
        if self._mm is None or self._ts is None:
            return None

        samples = await self._ts.count_unlabelled()
        win_rate = await self._ts.get_recent_win_rate()

        should_retrain = False
        reason = ""

        if samples >= _MIN_SAMPLES:
            should_retrain = True
            reason = f"enough_samples:{samples}"
        elif win_rate is not None and win_rate < _WINRATE_FLOOR:
            should_retrain = True
            reason = f"low_winrate:{win_rate:.2%}"

        if not should_retrain:
            return None

        return await self._retrain(reason, samples)

    async def force_retrain(self, reason: str = "manual") -> RetrainingResult:
        """Force an immediate retraining cycle."""
        samples = 0
        if self._ts:
            try:
                samples = await self._ts.count_unlabelled()
            except Exception:
                pass
        return await self._retrain(reason, samples)

    async def _retrain(self, reason: str, samples: int) -> RetrainingResult:
        """
        BUG-7 FIX: was hardcoding new_acc = 0.80 with a TODO comment.
        Real XGBoostTrainer.train_latest() is now called via executor.
        Falls back gracefully if trainer is unavailable.
        """
        start   = datetime.now(timezone.utc)
        old_acc = 0.0
        new_acc = 0.0

        try:
            logger.info("[Retraining] starting: reason=%s samples=%d", reason, samples)

            if self._mm:
                # Step 1: Read current model accuracy before retraining
                try:
                    current = self._mm.load_active("xgboost")
                    if current is not None and hasattr(current, "metadata"):
                        old_acc = float(current.metadata.get("accuracy", 0.0))
                    elif current is not None and hasattr(current, "accuracy"):
                        old_acc = float(current.accuracy or 0.0)
                except Exception as load_exc:
                    logger.warning("[Retraining] could not load current model: %s", load_exc)

                # Step 2: Actually run training - BUG-7 FIX (was new_acc = 0.80)
                try:
                    from backend.intelligence.xgboost_trainer import XGBoostTrainer
                    trainer = XGBoostTrainer()
                    loop = asyncio.get_event_loop()
                    train_result = await loop.run_in_executor(None, trainer.train_latest)
                    if train_result is not None:
                        new_acc = float(getattr(train_result, "accuracy", old_acc))
                        if new_acc > old_acc:
                            await loop.run_in_executor(
                                None, lambda: self._mm.save(train_result, "xgboost")
                            )
                            logger.info(
                                "[Retraining] model improved %.3f -> %.3f, saved",
                                old_acc, new_acc,
                            )
                        else:
                            logger.info(
                                "[Retraining] no improvement %.3f -> %.3f, keeping current",
                                old_acc, new_acc,
                            )
                    else:
                        new_acc = old_acc
                except ImportError:
                    logger.warning(
                        "[Retraining] XGBoostTrainer not available - cannot retrain"
                    )
                    new_acc = old_acc  # report honestly, not fake accuracy
                except Exception as train_exc:
                    logger.error("[Retraining] training failed: %s", train_exc)
                    new_acc = old_acc
            else:
                logger.warning("[Retraining] no model_manager configured - cannot retrain")

        except Exception as exc:
            logger.error("[Retraining] failed: %s", exc)

        duration = (datetime.now(timezone.utc) - start).total_seconds()
        now_str  = datetime.now(timezone.utc).isoformat()
        self._last_retrain = now_str

        result = RetrainingResult(
            triggered      = True,
            trigger_reason = reason,
            samples_used   = samples,
            old_accuracy   = old_acc,
            new_accuracy   = new_acc,
            improvement    = new_acc - old_acc,
            duration_s     = duration,
            completed_at   = now_str,
        )
        logger.info(
            "[Retraining] completed in %.1fs old=%.3f new=%.3f",
            duration, old_acc, new_acc,
        )
        return result


# Module-level singleton
retraining_service = RetrainingService()
