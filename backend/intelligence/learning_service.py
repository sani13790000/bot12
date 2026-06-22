from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RETRAIN_THRESHOLD   = 20
MIN_IMPROVEMENT_AUC = 0.005
DRIFT_THRESHOLD     = 0.08


class LearningStatus(str, Enum):
    IDLE        = "idle"
    TRAINING    = "training"
    EVALUATING  = "evaluating"
    DEPLOYING   = "deploying"
    DRIFT_ALERT = "drift_alert"
    ERROR       = "error"


@dataclass
class LearningCycle:
    """One retraining cycle record."""
    cycle_id:    str
    started_at:  datetime
    finished_at: Optional[datetime] = None
    old_auc:     float = 0.0
    new_auc:     float = 0.0
    deployed:    bool  = False
    reason:      str   = ""
    n_samples:   int   = 0
    error:       Optional[str] = None

    @property
    def improved(self) -> bool:
        # P-2 FIX: only True when new model is meaningfully better
        return self.new_auc - self.old_auc >= MIN_IMPROVEMENT_AUC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id":    self.cycle_id,
            "started_at":  self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "old_auc":     round(self.old_auc, 4),
            "new_auc":     round(self.new_auc, 4),
            "deployed":    self.deployed,
            "improved":    self.improved,
            "reason":      self.reason,
            "n_samples":   self.n_samples,
            "error":       self.error,
        }


class IntelligenceLearningService:
    """Self-learning loop - Phase P fixes P-1..P-5."""

    def __init__(self) -> None:
        self._retrain_lock = asyncio.Lock()
        self._status       = LearningStatus.IDLE
        self._new_trades   = 0
        self._cycles: List[LearningCycle] = []
        self._current_auc  = 0.0
        self._drift_score  = 0.0
        self._last_retrain = 0.0
        self._initialized  = False
        self._manager: Any = None
        self._memory:  Any = None

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            mgr = self._get_manager()
            versions = mgr.list_versions()
            if versions:
                self._current_auc = versions[0].accuracy
                logger.info("[Learning] initialized AUC=%.4f", self._current_auc)
            self._initialized = True
        except Exception as exc:
            logger.error("[Learning] initialize error: %s", exc)

    async def record_trade_outcome(self, outcome: Dict[str, Any]) -> None:
        try:
            tc = self._outcome_to_context(outcome)
            self._get_memory().add(tc)
            self._new_trades += 1
        except Exception as exc:
            logger.error("[Learning] record error: %s", exc)
            return
        await self._check_and_trigger()

    async def force_retrain(self, reason: str = "manual") -> LearningCycle:
        return await self._run_retrain(reason=reason)

    def get_status(self) -> Dict[str, Any]:
        return {
            "status":       self._status.value,
            "new_trades":   self._new_trades,
            "current_auc":  round(self._current_auc, 4),
            "drift_score":  round(self._drift_score, 4),
            "last_retrain": self._last_retrain,
            "total_cycles": len(self._cycles),
            "last_cycle":   self._cycles[-1].to_dict() if self._cycles else None,
        }

    def get_cycles(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self._cycles[-20:]]

    async def _check_and_trigger(self) -> None:
        should = False
        reason = ""
        if self._new_trades >= RETRAIN_THRESHOLD:
            should = True
            reason = f"threshold_{self._new_trades}"
        # P-3 FIX: real drift threshold
        if self._drift_score >= DRIFT_THRESHOLD:
            should = True
            reason = f"drift_{self._drift_score:.3f}"
            self._status = LearningStatus.DRIFT_ALERT
            logger.warning("[Learning] DRIFT ALERT score=%.3f", self._drift_score)
        busy = (LearningStatus.TRAINING, LearningStatus.EVALUATING, LearningStatus.DEPLOYING)
        if should and self._status not in busy:
            # P-1 FIX: asyncio.create_task = non-blocking
            asyncio.create_task(self._run_retrain(reason=reason))

    async def _run_retrain(self, reason: str = "auto") -> LearningCycle:
        import uuid
        cycle = LearningCycle(
            cycle_id=str(uuid.uuid4())[:8],
            started_at=datetime.now(timezone.utc),
            old_auc=self._current_auc,
            reason=reason,
        )
        acquired = False
        try:
            # P-5 FIX: lock with 5s timeout prevents deadlock
            try:
                await asyncio.wait_for(self._retrain_lock.acquire(), timeout=5.0)
                acquired = True
            except asyncio.TimeoutError:
                cycle.error = "lock_timeout"
                logger.warning("[Learning] retrain already running, skipped")
                return cycle

            self._status = LearningStatus.TRAINING
            # P-1 FIX: CPU-heavy work in thread pool
            result = await asyncio.to_thread(self._train_sync)
            self._status  = LearningStatus.EVALUATING
            cycle.new_auc   = result.get("auc", 0.0)
            cycle.n_samples = result.get("n_samples", 0)

            # P-2 FIX: deploy only when improved
            if cycle.improved:
                self._status = LearningStatus.DEPLOYING
                await asyncio.to_thread(self._deploy_sync, result)
                self._current_auc = cycle.new_auc
                cycle.deployed    = True
                self._new_trades  = 0
                self._drift_score = 0.0
                logger.info("[Learning] deployed AUC %.4f->%.4f", cycle.old_auc, cycle.new_auc)
            else:
                cycle.deployed = False
                logger.info("[Learning] skip deploy AUC %.4f not > %.4f+%.3f",
                            cycle.new_auc, cycle.old_auc, MIN_IMPROVEMENT_AUC)
        except Exception as exc:
            cycle.error = str(exc)
            logger.error("[Learning] retrain error: %s", exc, exc_info=True)
        finally:
            cycle.finished_at  = datetime.now(timezone.utc)
            self._cycles.append(cycle)
            self._last_retrain = time.time()
            self._status       = LearningStatus.IDLE
            if acquired:
                self._retrain_lock.release()
        return cycle

    def _train_sync(self) -> Dict[str, Any]:
        from backend.ai_prediction.dataset_builder import DatasetBuilder
        from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
        memory  = self._get_memory()
        dataset = DatasetBuilder().build(memory)
        if dataset.n_samples < 30:
            return {"auc": 0.0, "n_samples": dataset.n_samples}
        res = XGBoostTrainer().train(dataset)
        return {"auc": res.auc_roc, "f1": res.f1_score,
                "n_samples": dataset.n_samples, "model": res.model}

    def _deploy_sync(self, result: Dict[str, Any]) -> None:
        self._get_manager().register_version(
            model=result["model"], symbol="ALL", model_type="xgboost",
            accuracy=result["auc"], f1_score=result.get("f1", 0.0),
            n_samples=result.get("n_samples", 0),
            trained_at=datetime.now(timezone.utc),
        )

    def _outcome_to_context(self, outcome: Dict[str, Any]) -> Any:
        """P-4 FIX: safe conversion - no KeyError on partial dicts."""
        from backend.intelligence.trade_memory import TradeContext, TradeOutcome as TO
        return TradeContext(
            signal_id    = outcome.get("signal_id", "unknown"),
            symbol       = outcome.get("symbol", "UNKNOWN"),
            direction    = outcome.get("direction", "BUY"),
            entry_price  = float(outcome.get("entry_price", 0.0)),
            exit_price   = float(outcome.get("exit_price", 0.0)),
            pnl          = float(outcome.get("pnl", 0.0)),
            outcome      = TO.WIN if float(outcome.get("pnl", 0)) > 0 else TO.LOSS,
            smc_features = outcome.get("smc_features", {}),
            timestamp    = outcome.get("timestamp"),
        )

    def _get_manager(self) -> Any:
        if self._manager is None:
            from backend.ai_prediction.model_manager import ModelManager
            self._manager = ModelManager()
        return self._manager

    def _get_memory(self) -> Any:
        if self._memory is None:
            from backend.intelligence.trade_memory import TradeMemory
            self._memory = TradeMemory()
        return self._memory


_service: Optional[IntelligenceLearningService] = None


def get_learning_service() -> IntelligenceLearningService:
    global _service
    if _service is None:
        _service = IntelligenceLearningService()
    return _service
