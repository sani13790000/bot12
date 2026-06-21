"""
self_learning/learning_service.py -- Unified Learning Service
Phase D Fix (ARCH-5):

BEFORE: Two separate LearningService implementations:
  - backend/self_learning/learning_service.py    (drift-aware scheduler)
  - backend/intelligence/learning_service.py     (tight-coupled)

AFTER: Single canonical implementation here.
       intelligence/learning_service.py is now a thin re-export shim.

Design:
  - Dependency injection for all collaborators (DIP)
  - No direct imports from intelligence/ package (avoids circular deps)
  - asyncio.to_thread() for all blocking ML calls (TECH-4 fix)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LearningCycleResult:
    """Result of one complete learning cycle."""
    cycle_number: int = 0
    trades_processed: int = 0
    model_retrained: bool = False
    weights_adjusted: bool = False
    failures_analyzed: bool = False
    training_accuracy: float = 0.0
    training_f1: float = 0.0
    drift_detected: bool = False
    drift_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass
class LearningStats:
    """Aggregate statistics across all learning cycles."""
    total_cycles: int = 0
    successful_cycles: int = 0
    total_trades_processed: int = 0
    total_retrains: int = 0
    last_retrain_at: Optional[datetime] = None
    last_drift_detected_at: Optional[datetime] = None
    current_accuracy: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LearningService:
    """
    Orchestrates the self-learning loop with drift-aware scheduling.
    All collaborators injected via constructor (DIP).
    Blocking ML calls offloaded with asyncio.to_thread() (TECH-4).
    """

    CHECK_INTERVAL_SECONDS: int = 3600
    FORCE_RETRAIN_HOURS: int = 24
    MIN_SAMPLES_FOR_LEARN: int = 50
    MIN_SAMPLES_FOR_RETRAIN: int = 100
    MIN_SAMPLES_FOR_WEIGHTS: int = 200
    DRIFT_RETRAIN_THRESHOLD: float = 0.5

    def __init__(
        self,
        trade_memory: Optional[Any] = None,
        ml_engine: Optional[Any] = None,
        model_manager: Optional[Any] = None,
        retraining_service: Optional[Any] = None,
        weight_adjuster: Optional[Any] = None,
        failure_analyzer: Optional[Any] = None,
        db: Optional[Any] = None,
        on_cycle_complete: Optional[Callable[[LearningCycleResult], None]] = None,
    ) -> None:
        self._memory = trade_memory
        self._engine = ml_engine
        self._manager = model_manager
        self._retraining_svc = retraining_service
        self._weight_adjuster = weight_adjuster
        self._failure_analyzer = failure_analyzer
        self._db = db
        self._on_cycle_complete = on_cycle_complete
        self._stats = LearningStats()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_forced_retrain: Optional[datetime] = None

    async def start(self) -> None:
        if self._running:
            logger.warning("LearningService already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="learning_loop")
        logger.info("LearningService started (interval=%ds)", self.CHECK_INTERVAL_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LearningService stopped")

    async def record_trade(
        self,
        trade_context: Any,
        outcome: Any,
        *,
        trigger_learn: bool = True,
    ) -> None:
        if self._memory is not None:
            try:
                await asyncio.to_thread(self._memory.add, trade_context, outcome)
                self._stats.total_trades_processed += 1
            except Exception as exc:
                logger.warning("record_trade: memory.add failed -- %s", exc)
        if trigger_learn and self._sample_count() >= self.MIN_SAMPLES_FOR_LEARN:
            asyncio.create_task(
                self._run_cycle(),
                name=f"learning_cycle_{self._stats.total_cycles + 1}",
            )

    async def force_retrain(self) -> LearningCycleResult:
        logger.info("LearningService: force retrain requested")
        return await self._run_cycle(force=True)

    def get_stats(self) -> LearningStats:
        return self._stats

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                if not self._running:
                    break
                count = self._sample_count()
                if count < self.MIN_SAMPLES_FOR_LEARN:
                    logger.debug("LearningService: %d/%d samples -- skip", count, self.MIN_SAMPLES_FOR_LEARN)
                    continue
                await self._run_cycle(force=self._is_force_retrain_due())
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("LearningService loop error: %s", exc, exc_info=True)
                await asyncio.sleep(min(self.CHECK_INTERVAL_SECONDS * 2, 7200))

    async def _run_cycle(self, *, force: bool = False) -> LearningCycleResult:
        result = LearningCycleResult(cycle_number=self._stats.total_cycles + 1)
        contexts = self._get_contexts()
        result.trades_processed = len(contexts)
        try:
            # Step 1: Failure analysis
            if self._failure_analyzer is not None and len(contexts) >= self.MIN_SAMPLES_FOR_LEARN:
                try:
                    await asyncio.to_thread(self._failure_analyzer.analyze, contexts)
                    result.failures_analyzed = True
                except Exception as exc:
                    result.errors.append(f"failure_analysis: {exc}")

            # Step 2: Drift check
            drift_score = await self._check_drift()
            result.drift_score = drift_score
            result.drift_detected = drift_score >= self.DRIFT_RETRAIN_THRESHOLD

            # Step 3: Model retrain
            should_retrain = (
                force
                or result.drift_detected
                or self._is_force_retrain_due()
                or (len(contexts) >= self.MIN_SAMPLES_FOR_RETRAIN and self._engine_should_retrain())
            )
            if should_retrain and self._engine is not None:
                try:
                    # asyncio.to_thread avoids blocking event loop (TECH-4)
                    train_result = await asyncio.to_thread(self._engine.train, contexts)
                    result.model_retrained = True
                    result.training_accuracy = getattr(train_result, "accuracy", 0.0)
                    result.training_f1 = getattr(train_result, "f1_score", 0.0)
                    now = datetime.now(timezone.utc)
                    self._last_forced_retrain = now
                    self._stats.total_retrains += 1
                    self._stats.last_retrain_at = now
                    self._stats.current_accuracy = result.training_accuracy
                    if result.drift_detected:
                        self._stats.last_drift_detected_at = now
                    logger.info(
                        "Model retrained: acc=%.3f f1=%.3f drift=%.3f",
                        result.training_accuracy, result.training_f1, drift_score,
                    )
                except Exception as exc:
                    result.errors.append(f"retrain: {exc}")
                    logger.error("retrain error: %s", exc, exc_info=True)

            # Step 4: Weight adjustment
            if self._weight_adjuster is not None and len(contexts) >= self.MIN_SAMPLES_FOR_WEIGHTS:
                try:
                    await asyncio.to_thread(self._weight_adjuster.adjust, contexts)
                    result.weights_adjusted = True
                except Exception as exc:
                    result.errors.append(f"weight_adjust: {exc}")

        except Exception as exc:
            result.errors.append(f"cycle: {exc}")
            logger.error("cycle %d error: %s", result.cycle_number, exc, exc_info=True)
        finally:
            self._stats.total_cycles += 1
            if result.success:
                self._stats.successful_cycles += 1
            result.completed_at = datetime.now(timezone.utc)
            if self._on_cycle_complete is not None:
                try:
                    self._on_cycle_complete(result)
                except Exception:
                    pass
        return result

    # -- Helpers --

    def _sample_count(self) -> int:
        if self._memory is None:
            return 0
        try:
            count = getattr(self._memory, "count", None)
            return int(count()) if callable(count) else int(getattr(self._memory, "size", 0))
        except Exception:
            return 0

    def _get_contexts(self) -> List[Any]:
        if self._memory is None:
            return []
        try:
            get_all = getattr(self._memory, "get_all", None)
            return list(get_all()) if callable(get_all) else []
        except Exception:
            return []

    async def _check_drift(self) -> float:
        if self._engine is None:
            return 0.0
        try:
            fn = getattr(self._engine, "get_drift_info", None)
            if callable(fn):
                info = await asyncio.to_thread(fn)
                return float(info.get("drift_score", 0.0) if isinstance(info, dict) else 0.0)
        except Exception:
            pass
        return 0.0

    def _engine_should_retrain(self) -> bool:
        if self._engine is None:
            return False
        try:
            fn = getattr(self._engine, "should_retrain", None)
            return bool(fn()) if callable(fn) else False
        except Exception:
            return False

    def _is_force_retrain_due(self) -> bool:
        if self._last_forced_retrain is None:
            return True
        return (datetime.now(timezone.utc) - self._last_forced_retrain) >= timedelta(hours=self.FORCE_RETRAIN_HOURS)
