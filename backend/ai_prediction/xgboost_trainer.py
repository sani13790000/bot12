"""
Galaxy Vast AI Trading Platform
Module: XGBoostTrainer

Trains, validates, and optimizes an XGBoost model
for predicting trade success probability.

Features:
  - Cross-validation to prevent overfitting
  - Full performance metrics report
  - Feature importance logging
  - Hyperparameter tuning support
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrainingDataset:
    """Holds features and labels for model training."""
    X:             np.ndarray
    y:             np.ndarray
    feature_names: List[str]
    symbol:        str        = ""
    timeframe:     str        = ""

    @property
    def n_samples(self) -> int:
        return len(self.X)

    @property
    def positive_ratio(self) -> float:
        return float(self.y.mean()) if len(self.y) > 0 else 0.0


@dataclass
class TrainingResult:
    """Results from a completed training run."""
    model:              Any
    feature_importances: Dict[str, float]
    cv_scores:          List[float]
    cv_mean:            float
    cv_std:             float
    train_accuracy:     float
    val_accuracy:       float
    precision:          float
    recall:             float
    f1_score:           float
    duration_s:         float
    n_samples:          int
    params:             Dict[str, Any] = field(default_factory=dict)


class XGBoostTrainer:
    """
    Trains an XGBoost binary classifier to predict trade profitability.

    Usage:
        trainer = XGBoostTrainer()
        result  = trainer.train(dataset)
    """

    DEFAULT_PARAMS: Dict[str, Any] = {
        "n_estimators":      300,
        "max_depth":         6,
        "learning_rate":     0.05,
        "subsample":         0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "gamma":             0.1,
        "reg_alpha":         0.05,
        "reg_lambda":        1.0,
        "scale_pos_weight":  1.0,
        "objective":         "binary:logistic",
        "eval_metric":       "logloss",
        "random_state":      42,
        "n_jobs":            -1,
        "verbosity":         0,
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self._params = {**self.DEFAULT_PARAMS, **(params or {})}

    def train(
        self,
        dataset: TrainingDataset,
        cv_folds: int = 5,
        val_split: float = 0.2,
    ) -> TrainingResult:
        """
        Train the XGBoost model with cross-validation.

        Args:
            dataset:   TrainingDataset with X, y, feature_names
            cv_folds:  Number of cross-validation folds
            val_split: Fraction of data held out for final validation

        Returns:
            TrainingResult with model, metrics, and feature importances
        """
        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import cross_val_score, train_test_split
            from sklearn.metrics import (
                accuracy_score,
                precision_score, recall_score, f1_score,
            )
        except ImportError as e:
            raise ImportError(
                f"Required package missing: {e}. "
                "Run: pip install xgboost scikit-learn"
            ) from e

        t_start = time.perf_counter()
        logger.info(
            "Training XGBoost — samples=%d, features=%d, pos_ratio=%.1f%%",
            dataset.n_samples,
            len(dataset.feature_names),
            dataset.positive_ratio * 100,
        )

        # Train / validation split
        X_train, X_val, y_train, y_val = train_test_split(
            dataset.X, dataset.y,
            test_size    = val_split,
            stratify     = dataset.y,
            random_state = 42,
        )

        # Cross-validation
        model = XGBClassifier(**self._params)
        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv      = cv_folds,
            scoring = "roc_auc",
            n_jobs  = -1,
        )
        logger.info(
            "CV ROC-AUC: %.4f +/- %.4f",
            cv_scores.mean(), cv_scores.std()
        )

        # Final fit
        model.fit(
            X_train, y_train,
            eval_set          = [(X_val, y_val)],
            verbose           = False,
        )

        # Validation metrics
        y_pred = model.predict(X_val)
        val_acc   = accuracy_score(y_val, y_pred)
        precision = precision_score(y_val, y_pred, zero_division=0)
        recall    = recall_score(y_val, y_pred, zero_division=0)
        f1        = f1_score(y_val, y_pred, zero_division=0)

        # Train accuracy
        train_acc = accuracy_score(y_train, model.predict(X_train))

        # Feature importances
        importances = dict(zip(
            dataset.feature_names,
            model.feature_importances_.tolist(),
        ))
        top5 = sorted(importances.items(), key=lambda x: -x[1])[:5]
        logger.info("Top-5 features: %s", top5)

        duration = time.perf_counter() - t_start
        logger.info(
            "Training complete in %.2fs | val_acc=%.3f | f1=%.3f",
            duration, val_acc, f1
        )

        return TrainingResult(
            model               = model,
            feature_importances = importances,
            cv_scores           = cv_scores.tolist(),
            cv_mean             = float(cv_scores.mean()),
            cv_std              = float(cv_scores.std()),
            train_accuracy      = float(train_acc),
            val_accuracy        = float(val_acc),
            precision           = float(precision),
            recall              = float(recall),
            f1_score            = float(f1),
            duration_s          = duration,
            n_samples           = dataset.n_samples,
            params              = self._params.copy(),
        )

    def tune(
        self,
        dataset: TrainingDataset,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        cv_folds: int = 3,
    ) -> Dict[str, Any]:
        """
        Simple grid search over param_grid.
        Returns the best params found.
        """
        try:
            from sklearn.model_selection import GridSearchCV
            from xgboost import XGBClassifier
        except ImportError as e:
            raise ImportError(f"sklearn/xgboost required: {e}") from e

        grid = param_grid or {
            "max_depth":     [4, 6, 8],
            "learning_rate": [0.01, 0.05, 0.1],
            "n_estimators":  [100, 200, 300],
        }
        model  = XGBClassifier(**{k: v for k, v in self._params.items() if k not in grid})
        search = GridSearchCV(model, grid, cv=cv_folds, scoring="roc_auc", n_jobs=-1, verbose=0)
        search.fit(dataset.X, dataset.y)
        logger.info("Best params: %s (score=%.4f)", search.best_params_, search.best_score_)
        self._params.update(search.best_params_)
        return search.best_params_
