"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Retraining Service
هدف: بازآموزی خودکار هفتگی با مقایسه نسخه‌ها و rollback
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

from ..core.logger import get_logger
from .performance_tracker import ModelPerformanceRecord, PerformanceTracker
from .trade_dataset_generator import TradeDatasetGenerator
from .training_pipeline import TrainingConfig, TrainingPipeline, TrainingResult

logger = get_logger("self_learning.retraining_service")

DEFAULT_MODEL_DIR = Path("models/self_learning")


# ─────────────────────────────────────────────────────────────────────────────
# Enums & Models
# ─────────────────────────────────────────────────────────────────────────────

class RetrainingStatus(str, Enum):
    IDLE        = "IDLE"
    RUNNING     = "RUNNING"
    SUCCESS     = "SUCCESS"
    FAILED      = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED     = "SKIPPED"


@dataclass
class RetrainingJob:
    """اطلاعات یک چرخه بازآموزی."""
    job_id:         str      = ""
    symbol:         str      = "ALL"
    triggered_at:   datetime = field(default_factory=datetime.utcnow)
    completed_at:   Optional[datetime] = None
    status:         RetrainingStatus   = RetrainingStatus.IDLE
    reason:         str      = ""

    # نتایج
    old_model_id:   str   = ""
    new_model_id:   str   = ""
    old_auc:        float = 0.0
    new_auc:        float = 0.0
    auc_delta:      float = 0.0
    was_promoted:   bool  = False
    was_rolled_back:bool  = False
    error_message:  str   = ""
    training_samples: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id":          self.job_id,
            "symbol":          self.symbol,
            "triggered_at":    self.triggered_at.isoformat(),
            "completed_at":    self.completed_at.isoformat() if self.completed_at else None,
            "status":          self.status.value,
            "reason":          self.reason,
            "old_model_id":    self.old_model_id,
            "new_model_id":    self.new_model_id,
            "old_auc":         self.old_auc,
            "new_auc":         self.new_auc,
            "auc_delta":       self.auc_delta,
            "was_promoted":    self.was_promoted,
            "was_rolled_back": self.was_rolled_back,
            "error_message":   self.error_message,
            "training_samples":self.training_samples,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Retraining Service
# ─────────────────────────────────────────────────────────────────────────────

class RetrainingService:
    """
    سرویس بازآموزی خودکار هفتگی.

    قابلیت‌ها:
    • بازآموزی هفتگی با asyncio scheduler
    • مقایسه AUC مدل جدید با قدیمی
    • ترفیع خودکار اگر مدل جدید بهتر باشد
    • rollback اگر مدل جدید ضعیف‌تر باشد
    • نگهداری سابقه همه چرخه‌های بازآموزی
    """

    _CREATE_JOBS_TABLE = """
        CREATE TABLE IF NOT EXISTS self_learning_retrain_jobs (
            job_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol           VARCHAR(20)  NOT NULL,
            triggered_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            completed_at     TIMESTAMPTZ,
            status           VARCHAR(20)  NOT NULL DEFAULT 'IDLE',
            reason           TEXT         NOT NULL DEFAULT '',
            old_model_id     VARCHAR(100) NOT NULL DEFAULT '',
            new_model_id     VARCHAR(100) NOT NULL DEFAULT '',
            old_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
            new_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
            auc_delta        NUMERIC(6,4) NOT NULL DEFAULT 0,
            was_promoted     BOOLEAN      NOT NULL DEFAULT FALSE,
            was_rolled_back  BOOLEAN      NOT NULL DEFAULT FALSE,
            error_message    TEXT         NOT NULL DEFAULT '',
            training_samples INTEGER      NOT NULL DEFAULT 0,
            metadata         JSONB        NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_slrj_symbol ON self_learning_retrain_jobs (symbol);
        CREATE INDEX IF NOT EXISTS idx_slrj_status ON self_learning_retrain_jobs (status);
    """

    def __init__(
        self,
        db_pool:             asyncpg.Pool,
        dataset_generator:   TradeDatasetGenerator,
        training_pipeline:   TrainingPipeline,
        performance_tracker: PerformanceTracker,
        symbols:             List[str]              = None,
        retrain_interval_hours: int                 = 168,   # 7 روز
        min_new_trades:      int                    = 30,    # حداقل معاملات جدید برای trigger
        auc_improvement_threshold: float            = 0.005, # +0.5% برای ترفیع
    ) -> None:
        self._pool              = db_pool
        self._dataset           = dataset_generator
        self._pipeline          = training_pipeline
        self._tracker           = performance_tracker
        self._symbols           = symbols or ["XAUUSD", "EURUSD", "GBPUSD"]
        self._interval_hours    = retrain_interval_hours
        self._min_new_trades    = min_new_trades
        self._auc_threshold     = auc_improvement_threshold
        self._running           = False
        self._scheduler_task:   Optional[asyncio.Task] = None
        self._active_models:    Dict[str, TrainingResult] = {}   # symbol → best model
        self._job_history:      List[RetrainingJob]       = []

        logger.info(
            f"RetrainingService initialized | symbols={self._symbols} "
            f"| interval={self._interval_hours}h | min_trades={self._min_new_trades}"
        )

    # ─── Schema ───────────────────────────────────────────────────────────────

    async def ensure_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(self._CREATE_JOBS_TABLE)
        logger.info("RetrainingService schema ready")

    # ─── Scheduler ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """شروع scheduler هفتگی."""
        if self._running:
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"Retraining scheduler started — interval={self._interval_hours}h")

    async def stop(self) -> None:
        """توقف scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Retraining scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """حلقه اصلی scheduler — هر n ساعت یک‌بار اجرا می‌شود."""
        while self._running:
            try:
                logger.info("Scheduled retraining cycle starting...")
                for symbol in self._symbols:
                    await self.retrain_symbol(symbol, reason="scheduled_weekly")
            except Exception as exc:
                logger.error(f"Scheduler error: {exc}", exc_info=True)
            await asyncio.sleep(self._interval_hours * 3600)

    # ─── Retrain ──────────────────────────────────────────────────────────────

    async def retrain_symbol(
        self,
        symbol: str,
        reason: str = "manual",
        force:  bool = False,
    ) -> RetrainingJob:
        """
        اجرای یک چرخه بازآموزی برای یک نماد.

        Args:
            symbol: نماد (مثلاً XAUUSD)
            reason: دلیل trigger (scheduled_weekly / manual / performance_drop)
            force:  اگر True باشد حتی با نمونه کم اجرا می‌شود
        """
        import uuid as _uuid
        job = RetrainingJob(
            job_id     = str(_uuid.uuid4()),
            symbol     = symbol,
            reason     = reason,
            status     = RetrainingStatus.RUNNING,
        )
        await self._save_job(job)

        try:
            # ─── بررسی تعداد معاملات ───
            total = await self._dataset.count_trades(symbol=symbol, valid_only=True)
            job.training_samples = total

            if not force and total < self._pipeline._config.min_samples:
                job.status = RetrainingStatus.SKIPPED
                job.reason = f"insufficient_samples: {total} < {self._pipeline._config.min_samples}"
                logger.warning(f"Retrain skipped for {symbol}: {total} samples")
                await self._update_job(job)
                return job

            # ─── مدل فعلی ───
            current = self._active_models.get(symbol)
            job.old_model_id = current.model_id if current else ""
            job.old_auc      = current.test_auc  if current else 0.0

            # ─── ساخت Dataset ───
            X, y, feature_names = await self._dataset.build_dataset(symbol=symbol, valid_only=True)
            if len(X) == 0:
                job.status = RetrainingStatus.SKIPPED
                job.reason = "empty_dataset"
                await self._update_job(job)
                return job

            # ─── آموزش ───
            new_result = self._pipeline.train(X, y, feature_names, symbol=symbol)
            job.new_model_id = new_result.model_id
            job.new_auc      = new_result.test_auc
            job.auc_delta    = new_result.test_auc - job.old_auc

            # ─── تصمیم: ترفیع یا rollback ───
            if self._should_promote(job, new_result):
                self._active_models[symbol] = new_result
                job.was_promoted = True
                job.status       = RetrainingStatus.SUCCESS
                await self._tracker.record_model(new_result, promoted=True)
                logger.info(
                    f"Model promoted for {symbol} | "
                    f"AUC {job.old_auc:.4f} → {job.new_auc:.4f} (+{job.auc_delta:.4f})"
                )
            else:
                job.was_rolled_back = True
                job.status          = RetrainingStatus.ROLLED_BACK
                await self._tracker.record_model(new_result, promoted=False)
                logger.warning(
                    f"Model NOT promoted for {symbol} | "
                    f"new_AUC={job.new_auc:.4f} old_AUC={job.old_auc:.4f} "
                    f"threshold={self._auc_threshold}"
                )

        except Exception as exc:
            job.status        = RetrainingStatus.FAILED
            job.error_message = str(exc)
            logger.error(f"Retrain failed for {symbol}: {exc}", exc_info=True)

        finally:
            job.completed_at = datetime.utcnow()
            await self._update_job(job)
            self._job_history.append(job)

        return job

    async def rollback(self, symbol: str) -> bool:
        """rollback به مدل قبلی."""
        prev = await self._tracker.get_previous_model(symbol)
        if not prev:
            logger.warning(f"No previous model found for {symbol}")
            return False

        from .training_pipeline import TrainingResult as TR
        self._active_models[symbol] = prev
        logger.info(f"Rolled back {symbol} to model {prev.model_id}")
        return True

    # ─── وضعیت ────────────────────────────────────────────────────────────────

    def get_active_model(self, symbol: str) -> Optional[TrainingResult]:
        return self._active_models.get(symbol)

    def get_job_history(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
        jobs = [j for j in self._job_history if not symbol or j.symbol == symbol]
        return [j.to_dict() for j in jobs[-limit:]]

    async def get_status(self) -> Dict[str, Any]:
        active = {
            sym: {"model_id": m.model_id, "auc": m.test_auc, "version": m.version}
            for sym, m in self._active_models.items()
        }
        return {
            "running":           self._running,
            "interval_hours":    self._interval_hours,
            "symbols":           self._symbols,
            "active_models":     active,
            "total_jobs":        len(self._job_history),
            "last_job":          self._job_history[-1].to_dict() if self._job_history else None,
        }

    # ─── Private ──────────────────────────────────────────────────────────────

    def _should_promote(self, job: RetrainingJob, result: TrainingResult) -> bool:
        """آیا مدل جدید باید ترفیع بگیرد؟"""
        if not result.is_acceptable:
            return False
        if job.old_auc == 0.0:
            return True
        return job.auc_delta >= self._auc_threshold

    async def _save_job(self, job: RetrainingJob) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO self_learning_retrain_jobs
                    (job_id, symbol, status, reason, metadata)
                VALUES ($1, $2, $3, $4, $5)
                """,
                job.job_id, job.symbol, job.status.value,
                job.reason, json.dumps(job.to_dict()),
            )

    async def _update_job(self, job: RetrainingJob) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE self_learning_retrain_jobs SET
                    completed_at     = $2,
                    status           = $3,
                    old_model_id     = $4,
                    new_model_id     = $5,
                    old_auc          = $6,
                    new_auc          = $7,
                    auc_delta        = $8,
                    was_promoted     = $9,
                    was_rolled_back  = $10,
                    error_message    = $11,
                    training_samples = $12,
                    metadata         = $13
                WHERE job_id = $1
                """,
                job.job_id,
                job.completed_at,
                job.status.value,
                job.old_model_id,
                job.new_model_id,
                job.old_auc,
                job.new_auc,
                job.auc_delta,
                job.was_promoted,
                job.was_rolled_back,
                job.error_message,
                job.training_samples,
                json.dumps(job.to_dict()),
            )
