"""
Galaxy Vast AI Trading Platform
──────────────────────────────
UnifiedTypes — تیپ‌های یکپارچه

تمام کلاس‌های duplicate را در یک مکان جمع می‌کند.
کالرهای موجود حداکثر بدون تغییر کار می‌کنند.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ===========================================================================
# UnifiedTrainingResult
# Superset of:
#   - intelligence/ml_engine.py :: TrainingResult  (v1, 10 fields)
#   - self_learning/training_pipeline.py :: TrainingResult (v2, 25 fields)
# ===========================================================================

@dataclass
class UnifiedTrainingResult:
    """
    یک TrainingResult یکپارچه که هر دو نسخه v1 و v2 را پوشش می‌دهد.
    تمام فیلدها از هر دو نسخه حفظ شده‌اند.
    """
    # ---- v1 fields (ml_engine.TrainingResult) ----
    model_type:               Any    = None        # ModelType enum
    auc_roc:                  float  = 0.0
    accuracy:                 float  = 0.0
    precision:                float  = 0.0
    recall:                   float  = 0.0
    f1_score:                 float  = 0.0
    feature_importance:       Dict[str, float] = field(default_factory=dict)
    training_time_seconds:    float  = 0.0
    n_samples:                int    = 0
    is_reliable:              bool   = False

    # ---- v2 fields (training_pipeline.TrainingResult) ----
    model_id:                 str    = ""
    symbol:                   str    = "ALL"
    version:                  str    = "v1.0.0"
    trained_at:               datetime = field(default_factory=datetime.utcnow)
    train_auc:                float  = 0.0
    val_auc:                  float  = 0.0
    test_auc:                 float  = 0.0
    cv_auc_mean:              float  = 0.0
    cv_auc_std:               float  = 0.0
    total_samples:            int    = 0
    train_samples:            int    = 0
    test_samples:             int    = 0
    win_rate:                 float  = 0.0
    feature_count:            int    = 0
    model_path:               str    = ""
    scaler_path:              str    = ""
    metadata_path:            str    = ""
    is_acceptable:            bool   = False
    feature_names:            List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Backward-compat with v1 TrainingResult.summary"""
        mt = getattr(self.model_type, "value", str(self.model_type)) if self.model_type else "unified"
        return (
            f"{mt}: AUC={self.auc_roc:.3f} "
            f"Acc={self.accuracy:.3f} F1={self.f1_score:.3f} "
            f"n={self.n_samples or self.total_samples}"
        )

    # ---- converters ----

    @classmethod
    def from_ml_engine(cls, v1: Any) -> "UnifiedTrainingResult":
        """ml_engine.TrainingResult → UnifiedTrainingResult"""
        return cls(
            model_type            = getattr(v1, "model_type", None),
            auc_roc               = getattr(v1, "auc_roc", 0.0),
            accuracy              = getattr(v1, "accuracy", 0.0),
            precision             = getattr(v1, "precision", 0.0),
            recall                = getattr(v1, "recall", 0.0),
            f1_score              = getattr(v1, "f1_score", 0.0),
            feature_importance    = getattr(v1, "feature_importance", {}),
            training_time_seconds = getattr(v1, "training_time_seconds", 0.0),
            n_samples             = getattr(v1, "n_samples", 0),
            is_reliable           = getattr(v1, "is_reliable", False),
            # v2 mirrors
            test_auc              = getattr(v1, "auc_roc", 0.0),
            total_samples         = getattr(v1, "n_samples", 0),
            is_acceptable         = getattr(v1, "is_reliable", False),
        )

    @classmethod
    def from_pipeline(cls, v2: Any) -> "UnifiedTrainingResult":
        """training_pipeline.TrainingResult → UnifiedTrainingResult"""
        return cls(
            # v2 native
            model_id              = getattr(v2, "model_id", ""),
            symbol                = getattr(v2, "symbol", "ALL"),
            version               = getattr(v2, "version", "v1.0.0"),
            trained_at            = getattr(v2, "trained_at", datetime.utcnow()),
            train_auc             = getattr(v2, "train_auc", 0.0),
            val_auc               = getattr(v2, "val_auc", 0.0),
            test_auc              = getattr(v2, "test_auc", 0.0),
            cv_auc_mean           = getattr(v2, "cv_auc_mean", 0.0),
            cv_auc_std            = getattr(v2, "cv_auc_std", 0.0),
            accuracy              = getattr(v2, "accuracy", 0.0),
            precision             = getattr(v2, "precision", 0.0),
            recall                = getattr(v2, "recall", 0.0),
            f1_score              = getattr(v2, "f1_score", 0.0),
            total_samples         = getattr(v2, "total_samples", 0),
            train_samples         = getattr(v2, "train_samples", 0),
            test_samples          = getattr(v2, "test_samples", 0),
            win_rate              = getattr(v2, "win_rate", 0.0),
            feature_count         = getattr(v2, "feature_count", 0),
            model_path            = getattr(v2, "model_path", ""),
            scaler_path           = getattr(v2, "scaler_path", ""),
            metadata_path         = getattr(v2, "metadata_path", ""),
            is_acceptable         = getattr(v2, "is_acceptable", False),
            feature_names         = getattr(v2, "feature_names", []),
            feature_importance    = getattr(v2, "feature_importance", {}),
            # v1 mirrors
            auc_roc               = getattr(v2, "test_auc", 0.0),
            n_samples             = getattr(v2, "total_samples", 0),
            is_reliable           = getattr(v2, "is_acceptable", False),
        )

    def to_ml_engine_compat(self) -> dict:
        """Serialize as v1 TrainingResult-compatible dict."""
        return {
            "model_type":            self.model_type,
            "auc_roc":               self.auc_roc,
            "accuracy":              self.accuracy,
            "precision":             self.precision,
            "recall":                self.recall,
            "f1_score":              self.f1_score,
            "feature_importance":    self.feature_importance,
            "training_time_seconds": self.training_time_seconds,
            "n_samples":             self.n_samples or self.total_samples,
            "is_reliable":           self.is_reliable or self.is_acceptable,
        }

    def to_pipeline_compat(self) -> dict:
        """Serialize as v2 TrainingResult-compatible dict."""
        return {
            "model_id":          self.model_id,
            "symbol":            self.symbol,
            "version":           self.version,
            "trained_at":        self.trained_at.isoformat(),
            "train_auc":         self.train_auc,
            "val_auc":           self.val_auc,
            "test_auc":          self.test_auc or self.auc_roc,
            "cv_auc_mean":       self.cv_auc_mean,
            "cv_auc_std":        self.cv_auc_std,
            "accuracy":          self.accuracy,
            "precision":         self.precision,
            "recall":            self.recall,
            "f1_score":          self.f1_score,
            "total_samples":     self.total_samples or self.n_samples,
            "train_samples":     self.train_samples,
            "test_samples":      self.test_samples,
            "win_rate":          self.win_rate,
            "feature_count":     self.feature_count,
            "model_path":        self.model_path,
            "scaler_path":       self.scaler_path,
            "metadata_path":     self.metadata_path,
            "is_acceptable":     self.is_acceptable or self.is_reliable,
            "feature_names":     self.feature_names,
            "feature_importance":self.feature_importance,
        }


# ===========================================================================
# UnifiedMarketSession
# Single source of truth for TradingSession enum across all modules
# ===========================================================================

from backend.core.enums import TradingSession as UnifiedMarketSession  # noqa: E402


# ===========================================================================
# UnifiedTradeDirection
# Single source of truth for TradeDirection enum across all modules
# ===========================================================================

from backend.core.enums import TradeDirection as UnifiedTradeDirection  # noqa: E402


# ===========================================================================
# get_training_result_class()
# Factory: returns correct TrainingResult class for each caller
# ===========================================================================

def get_unified_result(source: str = "ml_engine") -> type:
    """
    Factory — برای کالرهایی که به یک TrainingResult مشخص نیاز دارند.

    source: 'ml_engine' | 'pipeline'
    """
    if source == "pipeline":
        try:
            from backend.self_learning.training_pipeline import TrainingResult
            return TrainingResult
        except ImportError:
            pass
    try:
        from backend.intelligence.ml_engine import TrainingResult
        return TrainingResult
    except ImportError:
        return UnifiedTrainingResult
