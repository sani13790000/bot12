"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Performance Tracker
هدف: ردیابی عملکرد مدل‌ها در طول زمان + مقایسه نسخه‌ها + rollback support
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
import numpy as np

from ..core.logger import get_logger

logger = get_logger("self_learning.performance_tracker")


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelPerformanceRecord:
    """رکورد عملکرد یک مدل در زمان ثبت."""
    record_id:     str      = ""
    model_id:      str      = ""
    symbol:        str      = ""
    version:       str      = ""
    registered_at: datetime = field(default_factory=datetime.utcnow)

    # متریک‌های آموزش
    train_auc:     float = 0.0
    val_auc:       float = 0.0
    test_auc:      float = 0.0
    cv_auc_mean:   float = 0.0
    cv_auc_std:    float = 0.0
    accuracy:      float = 0.0
    precision:     float = 0.0
    recall:        float = 0.0
    f1_score:      float = 0.0

    # اطلاعات dataset
    total_samples: int   = 0
    win_rate:      float = 0.0

    # وضعیت
    is_promoted:   bool  = False
    is_active:     bool  = False
    model_path:    str   = ""
    scaler_path:   str   = ""
    feature_names: List[str]       = field(default_factory=list)
    feature_importance: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id":     self.record_id,
            "model_id":      self.model_id,
            "symbol":        self.symbol,
            "version":       self.version,
            "registered_at": self.registered_at.isoformat(),
            "train_auc":     self.train_auc,
            "val_auc":       self.val_auc,
            "test_auc":      self.test_auc,
            "cv_auc_mean":   self.cv_auc_mean,
            "cv_auc_std":    self.cv_auc_std,
            "accuracy":      self.accuracy,
            "precision":     self.precision,
            "recall":        self.recall,
            "f1_score":      self.f1_score,
            "total_samples": self.total_samples,
            "win_rate":      self.win_rate,
            "is_promoted":   self.is_promoted,
            "is_active":     self.is_active,
            "model_path":    self.model_path,
            "scaler_path":   self.scaler_path,
            "feature_names": self.feature_names,
            "feature_importance": self.feature_importance,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Performance Tracker
# ─────────────────────────────────────────────────────────────────────────────

class PerformanceTracker:
    """
    ردیابی عملکرد همه نسخه‌های مدل.

    قابلیت‌ها:
    • ثبت هر مدل آموزش‌دیده در PostgreSQL
    • مقایسه نسخه‌ها (AUC trend)
    • نگهداری سابقه کامل
    • rollback support — بازیابی مدل قبلی
    • گزارش عملکرد در طول زمان
    """

    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS self_learning_model_registry (
            record_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            model_id           VARCHAR(100) NOT NULL UNIQUE,
            symbol             VARCHAR(20)  NOT NULL,
            version            VARCHAR(50)  NOT NULL,
            registered_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            train_auc          NUMERIC(6,4) NOT NULL DEFAULT 0,
            val_auc            NUMERIC(6,4) NOT NULL DEFAULT 0,
            test_auc           NUMERIC(6,4) NOT NULL DEFAULT 0,
            cv_auc_mean        NUMERIC(6,4) NOT NULL DEFAULT 0,
            cv_auc_std         NUMERIC(6,4) NOT NULL DEFAULT 0,
            accuracy           NUMERIC(6,4) NOT NULL DEFAULT 0,
            precision_score    NUMERIC(6,4) NOT NULL DEFAULT 0,
            recall_score       NUMERIC(6,4) NOT NULL DEFAULT 0,
            f1_score           NUMERIC(6,4) NOT NULL DEFAULT 0,
            total_samples      INTEGER      NOT NULL DEFAULT 0,
            win_rate           NUMERIC(6,4) NOT NULL DEFAULT 0,
            is_promoted        BOOLEAN      NOT NULL DEFAULT FALSE,
            is_active          BOOLEAN      NOT NULL DEFAULT FALSE,
            model_path         TEXT         NOT NULL DEFAULT '',
            scaler_path        TEXT         NOT NULL DEFAULT '',
            feature_names      JSONB        NOT NULL DEFAULT '[]',
            feature_importance JSONB        NOT NULL DEFAULT '{}',
            metadata           JSONB        NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_slmr_symbol   ON self_learning_model_registry (symbol);
        CREATE INDEX IF NOT EXISTS idx_slmr_active   ON self_learning_model_registry (symbol, is_active);
        CREATE INDEX IF NOT EXISTS idx_slmr_promoted ON self_learning_model_registry (symbol, is_promoted);
        CREATE INDEX IF NOT EXISTS idx_slmr_date     ON self_learning_model_registry (registered_at DESC);
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self._pool = db_pool
        logger.info("PerformanceTracker initialized")

    # ─── Schema ───────────────────────────────────────────────────────────────

    async def ensure_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(self._CREATE_TABLE_SQL)
        logger.info("PerformanceTracker schema ready")

    # ─── ثبت مدل ──────────────────────────────────────────────────────────────

    async def record_model(
        self,
        result:   "TrainingResult",   # type: ignore[name-defined]
        promoted: bool = False,
    ) -> str:
        """ثبت نتیجه آموزش یک مدل در registry."""
        import uuid as _uuid

        # اگر promoted شد → مدل‌های قبلی را غیرفعال کن
        if promoted:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE self_learning_model_registry SET is_active=FALSE WHERE symbol=$1",
                    result.symbol,
                )

        record_id = str(_uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO self_learning_model_registry (
                    record_id, model_id, symbol, version,
                    train_auc, val_auc, test_auc, cv_auc_mean, cv_auc_std,
                    accuracy, precision_score, recall_score, f1_score,
                    total_samples, win_rate,
                    is_promoted, is_active,
                    model_path, scaler_path,
                    feature_names, feature_importance, metadata
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                    $14,$15,$16,$17,$18,$19,$20,$21,$22
                )
                ON CONFLICT (model_id) DO UPDATE SET
                    is_promoted = EXCLUDED.is_promoted,
                    is_active   = EXCLUDED.is_active,
                    metadata    = EXCLUDED.metadata
                """,
                record_id, result.model_id, result.symbol, result.version,
                result.train_auc, result.val_auc, result.test_auc,
                result.cv_auc_mean, result.cv_auc_std,
                result.accuracy, result.precision, result.recall, result.f1_score,
                result.total_samples, result.win_rate,
                promoted, promoted,
                result.model_path, result.scaler_path,
                json.dumps(result.feature_names),
                json.dumps(result.feature_importance),
                json.dumps(result.to_dict()),
            )

        logger.info(
            f"Model registered: {result.model_id} | {result.symbol} | "
            f"AUC={result.test_auc:.4f} | promoted={promoted}"
        )
        return record_id

    # ─── بازیابی ──────────────────────────────────────────────────────────────

    async def get_active_model_record(self, symbol: str) -> Optional[ModelPerformanceRecord]:
        """بازیابی مدل فعال (promoted) برای یک نماد."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM self_learning_model_registry
                WHERE symbol=$1 AND is_active=TRUE
                ORDER BY registered_at DESC LIMIT 1
                """,
                symbol,
            )
        return self._row_to_record(row) if row else None

    async def get_previous_model(self, symbol: str) -> Optional["TrainingResult"]:
        """بازیابی مدل قبل از مدل فعال برای rollback."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM self_learning_model_registry
                WHERE symbol=$1 AND is_promoted=TRUE
                ORDER BY registered_at DESC LIMIT 2
                """,
                symbol,
            )

        if len(rows) < 2:
            return None

        prev_row = rows[1]   # مدل قبلی
        return self._row_to_training_result(prev_row)

    async def get_model_history(
        self,
        symbol: str,
        limit:  int = 20,
    ) -> List[Dict[str, Any]]:
        """تاریخچه همه مدل‌های ثبت‌شده برای یک نماد."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT record_id, model_id, version, registered_at,
                       test_auc, cv_auc_mean, accuracy, f1_score,
                       total_samples, is_promoted, is_active
                FROM   self_learning_model_registry
                WHERE  symbol=$1
                ORDER  BY registered_at DESC
                LIMIT  $2
                """,
                symbol, limit,
            )
        return [dict(r) for r in rows]

    # ─── مقایسه ───────────────────────────────────────────────────────────────

    async def compare_versions(self, symbol: str) -> Dict[str, Any]:
        """مقایسه عملکرد نسخه‌های مختلف مدل."""
        history = await self.get_model_history(symbol, limit=10)
        if not history:
            return {"symbol": symbol, "history": [], "trend": "NO_DATA"}

        aucs = [h["test_auc"] for h in history if h["test_auc"]]
        if len(aucs) >= 2:
            trend = "IMPROVING" if aucs[0] > aucs[-1] else "DEGRADING"
            auc_delta = round(float(aucs[0]) - float(aucs[-1]), 4)
        else:
            trend    = "STABLE"
            auc_delta = 0.0

        return {
            "symbol":    symbol,
            "history":   history,
            "trend":     trend,
            "auc_delta": auc_delta,
            "best_auc":  max(float(a) for a in aucs) if aucs else 0.0,
            "latest_auc":float(aucs[0]) if aucs else 0.0,
        }

    async def get_all_symbols_summary(self) -> List[Dict[str, Any]]:
        """خلاصه عملکرد همه نمادها."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, version, test_auc, accuracy, total_samples,
                    is_active, registered_at
                FROM   self_learning_model_registry
                ORDER  BY symbol, registered_at DESC
                """
            )
        return [dict(r) for r in rows]

    # ─── Private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: Any) -> ModelPerformanceRecord:
        return ModelPerformanceRecord(
            record_id          = str(row["record_id"]),
            model_id           = row["model_id"],
            symbol             = row["symbol"],
            version            = row["version"],
            registered_at      = row["registered_at"],
            train_auc          = float(row["train_auc"]),
            val_auc            = float(row["val_auc"]),
            test_auc           = float(row["test_auc"]),
            cv_auc_mean        = float(row["cv_auc_mean"]),
            cv_auc_std         = float(row["cv_auc_std"]),
            accuracy           = float(row["accuracy"]),
            precision          = float(row["precision_score"]),
            recall             = float(row["recall_score"]),
            f1_score           = float(row["f1_score"]),
            total_samples      = row["total_samples"],
            win_rate           = float(row["win_rate"]),
            is_promoted        = row["is_promoted"],
            is_active          = row["is_active"],
            model_path         = row["model_path"],
            scaler_path        = row["scaler_path"],
            feature_names      = json.loads(row["feature_names"])      if row["feature_names"] else [],
            feature_importance = json.loads(row["feature_importance"]) if row["feature_importance"] else {},
        )

    @staticmethod
    def _row_to_training_result(row: Any) -> "TrainingResult":   # type: ignore
        from .training_pipeline import TrainingResult
        r = TrainingResult()
        r.model_id    = row["model_id"]
        r.symbol      = row["symbol"]
        r.version     = row["version"]
        r.test_auc    = float(row["test_auc"])
        r.model_path  = row["model_path"]
        r.scaler_path = row["scaler_path"]
        return r
