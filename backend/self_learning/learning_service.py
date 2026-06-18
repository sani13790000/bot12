"""Learning Service — Phase 5: drift-aware scheduling, OOS validation, feature importance logging."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LearningService:
    """Orchestrates the self-learning loop with drift-aware scheduling."""

    CHECK_INTERVAL_SECONDS = 3600  # check every hour
    FORCE_RETRAIN_HOURS = 24
    MIN_SAMPLES_FOR_LEARN = 50
    DRIFT_RETRAIN_THRESHOLD = 0.5

    def __init__(
        self,
        trade_memory: Optional[Any] = None,
        ml_engine: Optional[Any] = None,
        model_manager: Optional[Any] = None,
        retraining_service: Optional[Any] = None,
        db=None,
    ):
        self._memory = trade_memory
        self._engine = ml_engine
        self._manager = model_manager
        self._retrainer = retraining_service
        self._db = db
        self._running = False
        self._learn_count = 0
        self._last_learn: Optional[datetime] = None
        self._last_drift_score: float = 0.0

    # ------------------------------------------------------------------ #
    #  PUBLIC API
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Start the background self-learning loop."""
        if self._running:
            logger.warning("[LearningService] already running")
            return
        self._running = True
        logger.info("[LearningService] started")
        asyncio.create_task(self._learn_loop())

    def stop(self) -> None:
        self._running = False
        logger.info("[LearningService] stopped")

    async def learn_now(self, force: bool = False) -> Dict[str, Any]:
        """Trigger a learning cycle immediately."""
        return await self._run_learn_cycle(force=force)

    def get_status(self) -> Dict[str, Any]:
        drift_info = {}
        if self._engine and hasattr(self._engine, "get_drift_info"):
            try:
                drift_info = self._engine.get_drift_info()
            except Exception:
                pass

        return {
            "running": self._running,
            "learn_count": self._learn_count,
            "last_learn": self._last_learn.isoformat() if self._last_learn else None,
            "last_drift_score": self._last_drift_score,
            "engine_trained": getattr(self._engine, "is_trained", False) if self._engine else False,
            "engine_version": getattr(self._engine, "model_version", "1.0") if self._engine else None,
            "drift_info": drift_info,
        }

    # ------------------------------------------------------------------ #
    #  LOOP
    # ------------------------------------------------------------------ #

    async def _learn_loop(self) -> None:
        while self._running:
            try:
                await self._run_learn_cycle()
            except Exception as exc:
                logger.error("[LearningService] loop error: %s", exc)
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    async def _run_learn_cycle(self, force: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "cycle_at": datetime.utcnow().isoformat(),
            "learned": False,
            "reason": None,
            "samples": 0,
            "accuracy": 0.0,
            "oos_accuracy": 0.0,
            "drift_score": 0.0,
            "model_version": None,
        }

        # 1. Get drift score
        drift_score = 0.0
        if self._engine and hasattr(self._engine, "get_drift_info"):
            try:
                info = self._engine.get_drift_info()
                drift_score = float(info.get("drift_score", 0.0))
                self._last_drift_score = drift_score
            except Exception:
                pass

        # 2. Decide if we should learn
        should_learn = force
        reason = "forced" if force else None

        if not should_learn and self._last_learn is None:
            should_learn = True
            reason = "initial"

        if not should_learn and drift_score > self.DRIFT_RETRAIN_THRESHOLD:
            should_learn = True
            reason = f"drift({drift_score:.3f})"

        if not should_learn and self._last_learn:
            age = datetime.utcnow() - self._last_learn
            if age > timedelta(hours=self.FORCE_RETRAIN_HOURS):
                should_learn = True
                reason = f"interval({age.total_seconds()/3600:.1f}h)"

        if not should_learn:
            result["reason"] = "no_learn_needed"
            result["drift_score"] = drift_score
            return result

        # 3. Delegate to RetrainingService if available
        if self._retrainer is not None:
            try:
                retrain_result = await self._retrainer.check_and_retrain()
                if retrain_result.get("retrained"):
                    tr = retrain_result.get("training_result") or {}
                    self._last_learn = datetime.utcnow()
                    self._learn_count += 1
                    result.update({
                        "learned": True,
                        "reason": reason,
                        "accuracy": tr.get("accuracy", 0.0),
                        "oos_accuracy": tr.get("avg_oos_accuracy", 0.0),
                        "drift_score": drift_score,
                        "model_version": tr.get("model_version"),
                    })
                    await self._log_feature_importance(tr)
                    return result
            except Exception as exc:
                logger.error("[LearningService] retrainer error: %s", exc)

        # 4. Direct engine fallback
        if self._engine is None:
            result["reason"] = "no_engine"
            return result

        contexts = await self._get_contexts()
        result["samples"] = len(contexts)

        if len(contexts) < self.MIN_SAMPLES_FOR_LEARN:
            result["reason"] = f"insufficient_data({len(contexts)})"
            return result

        try:
            if asyncio.iscoroutinefunction(getattr(self._engine, "train", None)):
                training_result = await self._engine.train(contexts)
            else:
                loop = asyncio.get_event_loop()
                training_result = await loop.run_in_executor(None, self._engine.train, contexts)

            if training_result and getattr(training_result, "success", False):
                self._last_learn = datetime.utcnow()
                self._learn_count += 1
                result.update({
                    "learned": True,
                    "reason": reason,
                    "accuracy": getattr(training_result, "accuracy", 0.0),
                    "oos_accuracy": getattr(training_result, "avg_oos_accuracy", 0.0),
                    "drift_score": drift_score,
                    "model_version": getattr(training_result, "model_version", None),
                })
                await self._log_feature_importance({
                    "feature_importance": getattr(training_result, "feature_importance", {}),
                    "model_version": getattr(training_result, "model_version", "1.0"),
                })
            else:
                error = getattr(training_result, "error", "unknown") if training_result else "none"
                result["reason"] = f"train_failed({error})"
        except Exception as exc:
            logger.error("[LearningService] train error: %s", exc)
            result["reason"] = f"exception({exc})"

        return result

    async def _get_contexts(self) -> List[Any]:
        if self._memory is None:
            return []
        try:
            if asyncio.iscoroutinefunction(getattr(self._memory, "get_all", None)):
                return await self._memory.get_all() or []
            return list(getattr(self._memory, "_memory", []) or [])
        except Exception as exc:
            logger.error("[LearningService] get_contexts error: %s", exc)
            return []

    async def _log_feature_importance(self, tr: Dict[str, Any]) -> None:
        if self._db is None:
            return
        fi = tr.get("feature_importance") or {}
        version = tr.get("model_version", "1.0")
        if not fi:
            return
        try:
            rows = [
                {
                    "symbol": "XAUUSD",
                    "model_version": version,
                    "feature_name": name,
                    "importance": float(imp),
                    "trained_at": datetime.utcnow().isoformat(),
                }
                for name, imp in fi.items()
            ]
            if rows and hasattr(self._db, "table"):
                self._db.table("feature_importance_log").insert(rows).execute()
        except Exception as exc:
            logger.warning("[LearningService] log_feature_importance error: %s", exc)
