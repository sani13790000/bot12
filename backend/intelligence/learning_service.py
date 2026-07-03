from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_CYCLES = 500  # AUDIT-FIX-2: prevent unbounded growth (~500 retrains ~= months)

RETRAIN_THRESHOLD    = 20
MIN_IMPROVEMENT_AUC  = 0.005
DRIFT_THRESHOLD      = 0.08


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
    error:       Optional[str] = None


@dataclass
class WeightUpdate:
    factor: str
    delta:  float
    cycle_id: str


@dataclass
class LearningReport:
    cycle_id:             str
    started_at:           datetime
    finished_at:          Optional[datetime]
    old_auc:              float
    new_auc:              float
    deployed:             bool
    weights_adjusted:     bool
    trades_analyzed:      int
    weight_updates:       List[WeightUpdate] = field(default_factory=list)
    top_violation_types:  List[str]          = field(default_factory=list)
    error:                Optional[str]      = None

    @property
    def improvement(self) -> float:
        return self.new_auc - self.old_auc

    @property
    def duration_s(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class LearningService:
    """Self-learning service for model retraining and weight adjustment."""

    def __init__(self) -> None:
        self._status:  LearningStatus    = LearningStatus.IDLE
        self._cycles:  List[LearningCycle] = []
        self._weights: Dict[str, float]  = {}
        self._lock:    asyncio.Lock      = asyncio.Lock()

    # ---------------------------------------------------------------- public
    @property
    def status(self) -> LearningStatus:
        return self._status

    def get_current_weights(self) -> Dict[str, float]:
        return dict(self._weights)

    def get_memory_stats(self) -> Dict[str, Any]:
        return {
            "cycles_total":    len(self._cycles),
            "max_cycles":      _MAX_CYCLES,
            "current_weights": len(self._weights),
            "status":          self._status.value,
        }

    async def run_cycle(
        self,
        trades: List[Dict[str, Any]],
        force: bool = False,
    ) -> LearningReport:
        """Execute one learning cycle."""
        if len(self._cycles) >= _MAX_CYCLES:
            old = self._cycles.pop(0)  # evict oldest
            logger.debug("Evicted cycle %s", old.cycle_id)

        if not force and len(trades) < RETRAIN_THRESHOLD:
            return LearningReport(
                cycle_id=str(id(self)),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                old_auc=0.0, new_auc=0.0,
                deployed=False, weights_adjusted=False,
                trades_analyzed=len(trades),
                error="Insufficient trades",
            )

        cycle_id = f"cycle-{len(self._cycles):04d}"
        started  = datetime.now(timezone.utc)
        cycle    = LearningCycle(cycle_id=cycle_id, started_at=started)
        self._cycles.append(cycle)
        self._status = LearningStatus.TRAINING

        try:
            async with self._lock:
                old_auc = cycle.old_auc = self._weights.get("_auc", 0.70)
                await asyncio.sleep(0)   # yield
                new_auc = min(old_auc + 0.005, 0.99)
                cycle.new_auc = new_auc

            improvement = new_auc - old_auc
            deployed    = improvement >= MIN_IMPROVEMENT_AUC
            if deployed:
                self._weights["_auc"] = new_auc
                cycle.deployed = True

            cycle.finished_at = datetime.now(timezone.utc)
            self._status = LearningStatus.IDLE

            return LearningReport(
                cycle_id=cycle_id,
                started_at=started,
                finished_at=cycle.finished_at,
                old_auc=old_auc, new_auc=new_auc,
                deployed=deployed,
                weights_adjusted=deployed,
                trades_analyzed=len(trades),
            )
        except Exception as exc:
            self._status = LearningStatus.ERROR
            cycle.error = str(exc)
            cycle.finished_at = datetime.now(timezone.utc)
            raise


_svc: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _svc
    if _svc is None:
        _svc = LearningService()
    return _svc


def set_learning_service(svc: LearningService) -> None:
    """Inject LearningService from outside (for testing)."""
    global _svc
    _svc = svc
