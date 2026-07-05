"""
backend/self_learning/retraining_service.py
Galaxy Vast AI Trading Platform

FIXES APPLIED:
  ARCH-R4-3: asyncio.get_event_loop() -> asyncio.get_running_loop()
             Deprecated in Python 3.10+, may raise RuntimeError in 3.12.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MIN_SAMPLES   = 100
_WINRATE_FLOOR = 0.45


@dataclass
class RetrainingResult:
    triggered:      bool
    trigger_reason: str
    samples_used:   int
    old_accuracy:   float
    new_accuracy:   float
    improvement:    float
    duration_s:     float
    completed_at:   str


class RetrainingService:
    def __init__(self, model_manager: Any = None, trade_store: Any = None) -> None:
        self._mm = model_manager
        self._ts = trade_store
        self._last_retrain: Optional[str] = None

    async def check_and_retrain(self) -> Optional[RetrainingResult]:
        if self._mm is None or self._ts is None:
            return None
        samples  = await self._ts.count_unlabelled()
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
        samples = 0
        if self._ts:
            try:
                samples = await self._ts.count_unlabelled()
            except Exception:
                pass
        return await self._retrain(reason, samples)

    async def _retrain(self, reason: str, samples: int) -> RetrainingResult:
        """
        ARCH-R4-3 FIX: asyncio.get_event_loop() replaced with asyncio.get_running_loop().
        get_event_loop() in async context:
          - Python 3.10: DeprecationWarning
          - Python 3.12: may raise RuntimeError
        get_running_loop() is the correct API inside an async function.
        """
        start   = datetime.now(timezone.utc)
        old_acc = 0.0
        new_acc = 0.0

        try:
            logger.info("[Retraining] starting: reason=%s samples=%d", reason, samples)

            if self._mm:
                try:
                    current = self._mm.load_active("xgboost")
                    if current is not None and hasattr(current, "metadata"):
                        old_acc = float(current.metadata.get("accuracy", 0.0))
                    elif current is not None and hasattr(current, "accuracy"):
                        old_acc = float(current.accuracy or 0.0)
                except Exception as load_exc:
                    logger.warning("[Retraining] could not load current model: %s", load_exc)

                try:
                    from backend.intelligence.xgboost_trainer import XGBoostTrainer
                    trainer = XGBoostTrainer()
                    # ARCH-R4-3 FIX: get_running_loop() not get_event_loop()
                    loop = asyncio.get_running_loop()
                    train_result = await loop.run_in_executor(None, trainer.train_latest)
                    if train_result is not None:
                        new_acc = float(getattr(train_result, "accuracy", old_acc))
                        if new_acc > old_acc:
                            await loop.run_in_executor(
                                None, lambda: self._mm.save(train_result, "xgboost")
                            )
                            logger.info("[Retraining] improved %.3f -> %.3f saved", old_acc, new_acc)
                        else:
                            logger.info("[Retraining] no improvement %.3f -> %.3f", old_acc, new_acc)
                    else:
                        new_acc = old_acc
                except ImportError:
                    logger.warning("[Retraining] XGBoostTrainer not available")
                    new_acc = old_acc
                except Exception as train_exc:
                    logger.error("[Retraining] training failed: %s", train_exc)
                    new_acc = old_acc
            else:
                logger.warning("[Retraining] no model_manager")

        except Exception as exc:
            logger.error("[Retraining] failed: %s", exc)

        duration = (datetime.now(timezone.utc) - start).total_seconds()
        now_str  = datetime.now(timezone.utc).isoformat()
        self._last_retrain = now_str
        result = RetrainingResult(
            triggered=True, trigger_reason=reason, samples_used=samples,
            old_accuracy=old_acc, new_accuracy=new_acc,
            improvement=new_acc - old_acc, duration_s=duration, completed_at=now_str,
        )
        logger.info("[Retraining] done: %.3f->%.3f in %.1fs", old_acc, new_acc, duration)
        return result

    def last_retrain_time(self) -> Optional[str]:
        return self._last_retrain

    def is_due(self, interval_hours: float = 24.0) -> bool:
        if self._last_retrain is None:
            return True
        try:
            last = datetime.fromisoformat(self._last_retrain)
            return (datetime.now(timezone.utc) - last).total_seconds() >= interval_hours * 3600
        except Exception:
            return True
