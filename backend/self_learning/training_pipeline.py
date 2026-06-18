"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Training Pipeline
هدف: pipeline کامل آموزش مدل با XGBoost + versioning
"""

from __future__ import annotations

import json
import os
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ..core.logger import get_logger

logger = get_logger("self_learning.training_pipeline")

# مسیر پیش‌فرض ذخیره مدل‌ها
DEFAULT_MODEL_DIR = Path("models/self_learning")


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrainingConfig:
    """تنظیمات آموزش مدل."""
    # XGBoost
    n_estimators:       int   = 500
    max_depth:          int   = 4
    learning_rate:      float = 0.05
    subsample:          float = 0.8
    colsample_bytree:   float = 0.8
    min_child_weight:   int   = 5
    gamma:              float = 0.1
    reg_alpha:          float = 0.1
    reg_lambda:         float = 1.0
    scale_pos_weight:   float = 1.0   # برای imbalanced data — محاسبه می‌شود
    early_stopping_rounds: int = 30

    # Cross-validation
    cv_folds:           int   = 5
    test_size:          float = 0.2
    random_state:       int   = 42

    # کنترل کیفیت
    min_auc_threshold:  float = 0.55  # مدل باید حداقل این AUC را داشته باشد
    min_samples:        int   = 50    # حداقل نمونه برای آموزش


@dataclass
class TrainingResult:
    """نتیجه کامل یک دوره آموزش."""
    model_id:       str      = field(default_factory=lambda: str(uuid.uuid4()))
    symbol:         str      = "ALL"
    version:        str      = "v1.0.0"
    trained_at:     datetime = field(default_factory=datetime.utcnow)

    # متریک‌های ارزیابی
    train_auc:      float = 0.0
    val_auc:        float = 0.0
    test_auc:       float = 0.0
    cv_auc_mean:    float = 0.0
    cv_auc_std:     float = 0.0
    accuracy:       float = 0.0
    precision:      float = 0.0
    recall:         float = 0.0
    f1_score:       float = 0.0

    # اطلاعات dataset
    total_samples:  int   = 0
    train_samples:  int   = 0
    test_samples:   int   = 0
    win_rate:       float = 0.0
    feature_count:  int   = 0

    # مسیر فایل مدل
    model_path:     str = ""
    scaler_path:    str = ""
    metadata_path:  str = ""

    # وضعیت
    is_acceptable:  bool = False   # آیا AUC از حد آستانه بالاتر است؟
    feature_names:  List[str] = field(default_factory=list)
    feature_importance: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id":      self.model_id,
            "symbol":        self.symbol,
            "version":       self.version,
            "trained_at":    self.trained_at.isoformat(),
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
            "train_samples": self.train_samples,
            "test_samples":  self.test_samples,
            "win_rate":      self.win_rate,
            "feature_count": self.feature_count,
            "model_path":    self.model_path,
            "scaler_path":   self.scaler_path,
            "metadata_path": self.metadata_path,
            "is_acceptable": self.is_acceptable,
            "feature_names": self.feature_names,
            "feature_importance": self.feature_importance,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Training Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TrainingPipeline:
    """
    Pipeline کامل آموزش XGBoost با versioning و cross-validation.

    مراحل:
    1. اعتبارسنجی dataset
    2. پیش‌پردازش (scaling + imbalance handling)
    3. Cross-validation (5-fold)
    4. آموزش مدل نهایی با early stopping
    5. Calibration (احتمال‌های واقعی‌تر)
    6. ذخیره مدل با versioning
    7. ساخت گزارش کامل
    """

    def __init__(
        self,
        model_dir: Path = DEFAULT_MODEL_DIR,
        config:    Optional[TrainingConfig] = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._config = config or TrainingConfig()
        logger.info(f"TrainingPipeline initialized | model_dir={self._model_dir}")

    # ─── Public ───────────────────────────────────────────────────────────────

    def train(
        self,
        X:             np.ndarray,
        y:             np.ndarray,
        feature_names: List[str],
        symbol:        str = "ALL",
        version:       Optional[str] = None,
    ) -> TrainingResult:
        """
        اجرای کامل pipeline آموزش.

        Args:
            X:             (n, features) dataset
            y:             (n,) labels — 1=WIN, 0=LOSS
            feature_names: نام ویژگی‌ها
            symbol:        نماد معاملاتی
            version:       نسخه (auto-generated اگر None باشد)

        Returns:
            TrainingResult با تمام متریک‌ها و مسیر فایل‌ها
        """
        cfg = self._config
        result = TrainingResult(
            symbol        = symbol,
            version       = version or self._generate_version(),
            total_samples = len(X),
            win_rate      = float(y.mean()),
            feature_count = X.shape[1],
            feature_names = feature_names,
        )

        # ─── اعتبارسنجی dataset ───
        if len(X) < cfg.min_samples:
            logger.error(f"Insufficient samples: {len(X)} < {cfg.min_samples}")
            raise ValueError(f"حداقل {cfg.min_samples} نمونه برای آموزش لازم است. موجود: {len(X)}")

        logger.info(f"Training start | symbol={symbol} | samples={len(X)} | win_rate={y.mean():.2%}")

        # ─── تقسیم train / test ───
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size    = cfg.test_size,
            random_state = cfg.random_state,
            stratify     = y,
        )
        result.train_samples = len(X_train)
        result.test_samples  = len(X_test)

        # ─── Scale ───
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s  = scaler.transform(X_test)

        # ─── محاسبه وزن کلاس‌ها ───
        neg = np.sum(y_train == 0)
        pos = np.sum(y_train == 1)
        scale_pos_weight = float(neg / pos) if pos > 0 else 1.0
        logger.info(f"Class balance — pos={pos} neg={neg} scale_pos_weight={scale_pos_weight:.2f}")

        # ─── Cross-validation ───
        cv_aucs = self._cross_validate(X_train_s, y_train, scale_pos_weight)
        result.cv_auc_mean = float(np.mean(cv_aucs))
        result.cv_auc_std  = float(np.std(cv_aucs))
        logger.info(f"CV AUC: {result.cv_auc_mean:.4f} ± {result.cv_auc_std:.4f}")

        # ─── آموزش مدل نهایی ───
        X_tr2, X_val2, y_tr2, y_val2 = train_test_split(
            X_train_s, y_train,
            test_size    = 0.15,
            random_state = cfg.random_state,
            stratify     = y_train,
        )

        model = XGBClassifier(
            n_estimators          = cfg.n_estimators,
            max_depth             = cfg.max_depth,
            learning_rate         = cfg.learning_rate,
            subsample             = cfg.subsample,
            colsample_bytree      = cfg.colsample_bytree,
            min_child_weight      = cfg.min_child_weight,
            gamma                 = cfg.gamma,
            reg_alpha             = cfg.reg_alpha,
            reg_lambda            = cfg.reg_lambda,
            scale_pos_weight      = scale_pos_weight,
            use_label_encoder     = False,
            eval_metric           = "auc",
            early_stopping_rounds = cfg.early_stopping_rounds,
            random_state          = cfg.random_state,
            n_jobs                = -1,
        )

        model.fit(
            X_tr2, y_tr2,
            eval_set         = [(X_val2, y_val2)],
            verbose          = False,
        )

        # ─── Calibration ───
        calibrated = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
        calibrated.fit(X_val2, y_val2)

        # ─── متریک‌ها ───
        result.train_auc = roc_auc_score(y_tr2,   model.predict_proba(X_tr2)[:, 1])
        result.val_auc   = roc_auc_score(y_val2,  model.predict_proba(X_val2)[:, 1])
        result.test_auc  = roc_auc_score(y_test,  calibrated.predict_proba(X_test_s)[:, 1])

        y_pred = calibrated.predict(X_test_s)
        result.accuracy  = accuracy_score(y_test,  y_pred)
        result.precision = precision_score(y_test, y_pred, zero_division=0)
        result.recall    = recall_score(y_test,    y_pred, zero_division=0)
        result.f1_score  = f1_score(y_test,        y_pred, zero_division=0)

        result.is_acceptable = result.test_auc >= cfg.min_auc_threshold

        # ─── Feature importance ───
        importances = model.feature_importances_
        result.feature_importance = {
            name: round(float(imp), 6)
            for name, imp in sorted(
                zip(feature_names, importances),
                key=lambda x: x[1], reverse=True,
            )
        }

        # ─── ذخیره فایل‌ها ───
        result.model_path, result.scaler_path, result.metadata_path = (
            self._save_artifacts(calibrated, scaler, result, symbol)
        )

        logger.info(
            f"Training complete | AUC={result.test_auc:.4f} "
            f"| acc={result.accuracy:.2%} | acceptable={result.is_acceptable}"
        )
        return result

    # ─── Private ──────────────────────────────────────────────────────────────

    def _cross_validate(
        self,
        X: np.ndarray,
        y: np.ndarray,
        scale_pos_weight: float,
    ) -> List[float]:
        """5-fold Stratified Cross-Validation."""
        cfg = self._config
        skf  = StratifiedKFold(n_splits=cfg.cv_folds, shuffle=True, random_state=cfg.random_state)
        aucs: List[float] = []

        for fold, (tr_idx, val_idx) in enumerate(skf.split(X, y), 1):
            X_tr, X_val = X[tr_idx], X[val_idx]
            y_tr, y_val = y[tr_idx], y[val_idx]

            clf = XGBClassifier(
                n_estimators     = 300,
                max_depth        = cfg.max_depth,
                learning_rate    = cfg.learning_rate,
                subsample        = cfg.subsample,
                colsample_bytree = cfg.colsample_bytree,
                scale_pos_weight = scale_pos_weight,
                use_label_encoder= False,
                eval_metric      = "auc",
                random_state     = cfg.random_state,
                n_jobs           = -1,
            )
            clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
            auc = roc_auc_score(y_val, clf.predict_proba(X_val)[:, 1])
            aucs.append(auc)
            logger.debug(f"  Fold {fold}/{cfg.cv_folds} AUC={auc:.4f}")

        return aucs

    def _save_artifacts(
        self,
        model:   Any,
        scaler:  StandardScaler,
        result:  TrainingResult,
        symbol:  str,
    ) -> Tuple[str, str, str]:
        """ذخیره مدل، scaler و metadata با versioning."""
        symbol_dir = self._model_dir / symbol.lower().replace("/", "_")
        symbol_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_name = f"{symbol.lower()}_{result.version}_{ts}"

        model_path    = symbol_dir / f"{base_name}_model.pkl"
        scaler_path   = symbol_dir / f"{base_name}_scaler.pkl"
        metadata_path = symbol_dir / f"{base_name}_metadata.json"

        with open(model_path,  "wb") as f: pickle.dump(model,  f, protocol=5)
        with open(scaler_path, "wb") as f: pickle.dump(scaler, f, protocol=5)

        metadata = result.to_dict()
        metadata["model_path"]    = str(model_path)
        metadata["scaler_path"]   = str(scaler_path)
        metadata["metadata_path"] = str(metadata_path)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Artifacts saved: {symbol_dir}")
        return str(model_path), str(scaler_path), str(metadata_path)

    @staticmethod
    def _generate_version() -> str:
        ts = datetime.utcnow()
        return f"v{ts.year}.{ts.month:02d}.{ts.day:02d}_{ts.hour:02d}{ts.minute:02d}"
