"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: XGBoostTrainer

وظیفه:
  آموزش، اعتبارسنجی و بهینه‌سازی مدل XGBoost
  برای پیش‌بینی موفقیت معاملات.

جزئیات:
  • آموزش با cross-validation برای جلوگیری از overfitting
  • گزارش کامل performance metrics
  • ذخیره feature importance
  • پشتیبانی از hyperparameter tuning
"""

from __future__ import annotations

import os
import pickle
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.logger import get_logger
from .dataset_builder import TrainingDataset

logger = get_logger("ai_prediction.xgboost_trainer")


@dataclass
class TrainingResult:
    """
    نتایج کامل یک دوره آموزش.

    Attributes:
        model: مدل آموزش‌دیده XGBoost
        auc_roc: سطح زیر منحنی ROC (0.5 = تصادفی، 1.0 = کامل)
        accuracy: دقت کلی
        precision: دقت پیش‌بینی‌های مثبت
        recall: نرخ تشخیص موارد مثبت
        f1_score: میانگین هارمونیک precision و recall
        feature_importance: اهمیت هر ویژگی
        training_time_seconds: زمان آموزش
        n_estimators_used: تعداد درخت‌های استفاده‌شده (early stopping)
        cv_scores: نتایج cross-validation
        is_reliable: آیا مدل قابل اعتماد است؟ (AUC ≥ 0.60)
    """
    model:                  Any
    auc_roc:                float
    accuracy:               float
    precision:              float
    recall:                 float
    f1_score:               float
    feature_importance:     Dict[str, float]
    training_time_seconds:  float
    n_estimators_used:      int
    cv_scores:              List[float]
    is_reliable:            bool

    @property
    def cv_mean(self) -> float:
        return float(np.mean(self.cv_scores)) if self.cv_scores else 0.0

    @property
    def cv_std(self) -> float:
        return float(np.std(self.cv_scores)) if self.cv_scores else 0.0


class XGBoostTrainer:
    """
    آموزش‌دهنده مدل XGBoost برای Galaxy Vast.

    این کلاس تمام منطق آموزش، اعتبارسنجی و بهینه‌سازی را
    در یک رابط ساده و قابل تست کپسوله می‌کند.
    """

    # حداقل AUC برای اینکه مدل قابل اعتماد تلقی شود
    MIN_RELIABLE_AUC: float = 0.60

    # پارامترهای پیش‌فرض XGBoost — بهینه‌شده برای داده‌های مالی
    DEFAULT_PARAMS: Dict[str, Any] = {
        "objective":        "binary:logistic",
        "eval_metric":      "auc",
        "max_depth":        4,          # کم — جلوگیری از overfitting
        "learning_rate":    0.05,       # کند — دقت بیشتر
        "n_estimators":     500,        # با early stopping
        "min_child_weight": 5,          # حداقل نمونه در برگ
        "subsample":        0.8,        # 80% داده در هر درخت
        "colsample_bytree": 0.8,        # 80% ویژگی در هر درخت
        "gamma":            0.1,        # regularization
        "reg_alpha":        0.1,        # L1 regularization
        "reg_lambda":       1.0,        # L2 regularization
        "random_state":     42,
        "n_jobs":           -1,         # همه CPU cores
        "verbosity":        0,
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self._params = {**self.DEFAULT_PARAMS, **(params or {})}

    def train(
        self,
        dataset: TrainingDataset,
        test_size:     float = 0.20,
        cv_folds:      int   = 5,
        early_stopping: int  = 30,
    ) -> TrainingResult:
        """
        آموزش کامل مدل با cross-validation و early stopping.

        Args:
            dataset:       dataset آماده از DatasetBuilder
            test_size:     نسبت داده تست (پیش‌فرض 20%)
            cv_folds:      تعداد fold برای cross-validation
            early_stopping: تعداد دور بدون بهبود قبل از توقف

        Returns:
            TrainingResult با مدل و تمام metrics
        """
        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
            from sklearn.metrics import (
                roc_auc_score, accuracy_score,
                precision_score, recall_score, f1_score,
            )
        except ImportError as e:
            raise ImportError(
                f"required package missing: {e}
"
                "run: pip install xgboost scikit-learn"
            ) from e

        t_start = time.perf_counter()
        logger.info(
            "training XGBoost — samples=%d, features=%d, pos_ratio=%.1f%%",
            dataset.n_samples, len(dataset.feature_names),
            100 * dataset.win_rate,
        )

        # تقسیم به train / test با stratify (حفظ نسبت کلاس‌ها)
        X_train, X_test, y_train, y_test = train_test_split(
            dataset.X, dataset.y,
            test_size=test_size,
            random_state=42,
            stratify=dataset.y,
        )

        # تنظیم scale_pos_weight برای imbalanced data
        params = {
            **self._params,
            "scale_pos_weight": dataset.class_weight_ratio,
        }

        # ساخت و آموزش مدل با early stopping
        model = XGBClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            early_stopping_rounds=early_stopping,
            verbose=False,
        )

        # پیش‌بینی و محاسبه metrics
        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.50).astype(int)

        auc       = float(roc_auc_score(y_test, y_prob))
        accuracy  = float(accuracy_score(y_test, y_pred))
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall    = float(recall_score(y_test, y_pred, zero_division=0))
        f1        = float(f1_score(y_test, y_pred, zero_division=0))

        # cross-validation روی کل dataset
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
        cv_model = XGBClassifier(**params)
        cv_scores = cross_val_score(cv_model, dataset.X, dataset.y, cv=cv, scoring="roc_auc")

        # feature importance
        importance_raw = model.feature_importances_
        importance = {
            name: float(imp)
            for name, imp in zip(dataset.feature_names, importance_raw)
        }
        # مرتب‌سازی نزولی
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

        elapsed = time.perf_counter() - t_start

        logger.info(
            "training done — AUC=%.3f, accuracy=%.3f, F1=%.3f, time=%.1fs",
            auc, accuracy, f1, elapsed,
        )

        return TrainingResult(
            model                 = model,
            auc_roc               = auc,
            accuracy              = accuracy,
            precision             = precision,
            recall                = recall,
            f1_score              = f1,
            feature_importance    = importance,
            training_time_seconds = elapsed,
            n_estimators_used     = model.best_iteration + 1 if hasattr(model, "best_iteration") else params["n_estimators"],
            cv_scores             = cv_scores.tolist(),
            is_reliable           = auc >= self.MIN_RELIABLE_AUC,
        )

    def save(self, result: TrainingResult, path: str) -> None:
        """ذخیره مدل روی disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(result.model, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("model saved to %s", path)

    def load(self, path: str) -> Any:
        """بارگذاری مدل از disk."""
        with open(path, "rb") as f:
            model = pickle.load(f)
        logger.info("model loaded from %s", path)
        return model
