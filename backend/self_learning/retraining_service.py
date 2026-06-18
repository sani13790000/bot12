"""Retraining Service — Phase 5: drift-triggered retrain, walk-forward validation, model registry."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrainingService:
    """Orchestrates periodic and drift-triggered model retraining."""

    MIN_SAMPLES = 50
    RETRAIN_INTERVAL_HOURS = 24
    DRIFT_THRESHOLD = 0.5
    OVERFIT_THRESHOLD = 1.3  # train_acc / test_acc > 1.3 → suspect

    def __init__(
        self,
        trade_memory: Optional[Any] = None,
        ml_engine: Optional[Any] = None,
        model_manager: Optional[Any] = None,
        db=None,
    ):
        self._memory = trade_memory
        self._engine = ml_engine
        self._manager = model_manager
        self._db = db
        self._last_retrain: Optional[datetime] = None
        self._retrain_count = 0
        self._running = False

    # ------------------------------------------------------------------ #
    #  PUBLIC API
    # ------------------------------------------------------------------ #

    async def run_forever(self, interval_hours: float = 6.0) -> None:
        """Background loop: retrain every N hours or on drift."""
        self._running = True
        logger.info("[RetrainingService] background loop started, interval=%.1fh", interval_hours)
        while self._running:
            try:
                await self.check_and_retrain()
            except Exception as exc:
                logger.error("[RetrainingService] loop error: %s", exc)
            await asyncio.sleep(interval_hours * 3600)

    def stop(self) -> None:
        self._running = False

    async def check_and_retrain(self) -> Dict[str, Any]:
        """Check drift + staleness, retrain if needed. Returns status dict."""
        result: Dict[str, Any] = {
            "checked_at": datetime.utcnow().isoformat(),
            "retrained": False,
            "reason": None,
            "training_result": None,
        }

        # 1. Check if engine says retrain needed (drift or staleness)
        should_retrain = False
        reason = None

        if self._engine is not None:
            try:
                should_retrain = self._engine.should_retrain()
                if should_retrain:
                    drift_info = self._engine.get_drift_info() if hasattr(self._engine, "get_drift_info") else {}
                    drift_score = drift_info.get("drift_score", 0.0)
                    if drift_score > self.DRIFT_THRESHOLD:
                        reason = f"concept_drift(score={drift_score:.3f})"
                    else:
                        reason = "staleness(>24h)"
            except Exception as exc:
                logger.warning("[RetrainingService] should_retrain check error: %s", exc)

        # 2. Force retrain if interval exceeded
        if not should_retrain and self._last_retrain is not None:
            age = datetime.utcnow() - self._last_retrain
            if age > timedelta(hours=self.RETRAIN_INTERVAL_HOURS):
                should_retrain = True
                reason = f"interval({age.total_seconds()/3600:.1f}h)"

        # 3. First run always retrains
        if not should_retrain and self._last_retrain is None:
            should_retrain = True
            reason = "initial_train"

        if not should_retrain:
            result["reason"] = "no_retrain_needed"
            return result

        # 4. Get training data
        contexts = await self._get_training_contexts()
        if len(contexts) < self.MIN_SAMPLES:
            result["reason"] = f"insufficient_data({len(contexts)}<{self.MIN_SAMPLES})"
            logger.info("[RetrainingService] skip: %s", result["reason"])
            return result

        # 5. Train
        logger.info("[RetrainingService] retraining, reason=%s, samples=%d", reason, len(contexts))
        training_result = await self._run_training(contexts)

        if training_result and getattr(training_result, "success", False):
            # 6. Validate walk-forward folds
            folds = getattr(training_result, "walk_forward_folds", [])
            if folds:
                avg_overfit = sum(f.overfit_ratio for f in folds) / len(folds)
                if avg_overfit > self.OVERFIT_THRESHOLD:
                    logger.warning(
                        "[RetrainingService] overfit detected: avg_overfit=%.2f > %.2f — model saved but flagged",
                        avg_overfit, self.OVERFIT_THRESHOLD
                    )
                    training_result.notes = f"overfit_warning(ratio={avg_overfit:.2f})"

            # 7. Save to model manager
            if self._manager is not None:
                try:
                    version = self._manager.save_model("XAUUSD", None, training_result)
                    logger.info("[RetrainingService] model saved v%s", version)
                except Exception as exc:
                    logger.error("[RetrainingService] save error: %s", exc)

            # 8. Persist to DB
            await self._persist_retrain_job(training_result, reason)

            self._last_retrain = datetime.utcnow()
            self._retrain_count += 1
            result["retrained"] = True
            result["reason"] = reason
            result["training_result"] = {
                "accuracy": getattr(training_result, "accuracy", 0),
                "f1_score": getattr(training_result, "f1_score", 0),
                "n_samples": getattr(training_result, "n_samples", 0),
                "avg_oos_accuracy": getattr(training_result, "avg_oos_accuracy", 0),
                "drift_status": str(getattr(training_result, "drift_status", "stable")),
                "model_version": getattr(training_result, "model_version", "1.0"),
            }
        else:
            error = getattr(training_result, "error", "unknown") if training_result else "engine_unavailable"
            result["reason"] = f"train_failed({error})"
            logger.error("[RetrainingService] training failed: %s", error)

        return result

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "retrain_count": self._retrain_count,
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
            "engine_trained": getattr(self._engine, "is_trained", False) if self._engine else False,
        }

    # ------------------------------------------------------------------ #
    #  INTERNAL
    # ------------------------------------------------------------------ #

    async def _get_training_contexts(self) -> List[Any]:
        if self._memory is None:
            return []
        try:
            if asyncio.iscoroutinefunction(getattr(self._memory, "get_all", None)):
                return await self._memory.get_all() or []
            result = getattr(self._memory, "_memory", []) or []
            return list(result)
        except Exception as exc:
            logger.error("[RetrainingService] get_training_contexts error: %s", exc)
            return []

    async def _run_training(self, contexts: List[Any]) -> Optional[Any]:
        if self._engine is None:
            return None
        try:
            if asyncio.iscoroutinefunction(getattr(self._engine, "train", None)):
                return await self._engine.train(contexts)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._engine.train, contexts)
        except Exception as exc:
            logger.error("[RetrainingService] _run_training error: %s", exc)
            return None

    async def _persist_retrain_job(self, result: Any, reason: str) -> None:
        if self._db is None:
            return
        try:
            payload = {
                "triggered_at": datetime.utcnow().isoformat(),
                "reason": reason,
                "success": getattr(result, "success", False),
                "accuracy": getattr(result, "accuracy", 0.0),
                "f1_score": getattr(result, "f1_score", 0.0),
                "n_samples": getattr(result, "n_samples", 0),
                "avg_oos_accuracy": getattr(result, "avg_oos_accuracy", 0.0),
                "avg_overfit_ratio": getattr(result, "avg_overfit_ratio", 1.0),
                "drift_score": getattr(result, "drift_score", 0.0),
                "model_version": getattr(result, "model_version", "1.0"),
                "error": getattr(result, "error", None),
            }
            if hasattr(self._db, "table"):
                self._db.table("self_learning_retrain_jobs").insert(payload).execute()
        except Exception as exc:
            logger.warning("[RetrainingService] persist error: %s", exc)
