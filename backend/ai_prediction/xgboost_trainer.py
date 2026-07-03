"""
Galaxy Vast AI Trading Platform
XGBoost Trainer -- Feature engineering and model training
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    import numpy as np
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    logger.warning("xgboost not installed -- trainer disabled")


@dataclass
class TrainingConfig:
    n_estimators:   int   = 100
    max_depth:      int   = 6
    learning_rate:  float = 0.1
    subsample:      float = 0.8
    colsample:      float = 0.8
    early_stopping: int   = 10
    eval_metric:    str   = "logloss"


@dataclass
class TrainingResult:
    model:          Any
    feature_names:  list[str]
    train_score:    float
    val_score:      float
    n_estimators:   int
    best_iteration: int


class XGBoostTrainer:
    """Train XGBoost models for trade signal classification."""

    def __init__(self, config: Optional[TrainingConfig] = None) -> None:
        self.config = config or TrainingConfig()
        self._model: Optional[Any] = None
        self._feature_names: list[str] = []

    def train(
        self,
        X_train: Any,
        y_train: Any,
        X_val: Any,
        y_val: Any,
        feature_names: Optional[list[str]] = None,
    ) -> TrainingResult:
        """Train the XGBoost model."""
        if not HAS_XGBOOST:
            raise RuntimeError("xgboost is not installed")

        self._feature_names = feature_names or [f"f{i}" for i in range(X_train.shape[1])]

        params = {
            "n_estimators":        self.config.n_estimators,
            "max_depth":           self.config.max_depth,
            "learning_rate":       self.config.learning_rate,
            "subsample":           self.config.subsample,
            "colsample_bytree":    self.config.colsample,
            "eval_metric":         self.config.eval_metric,
            "use_label_encoder":   False,
            "early_stopping_rounds": self.config.early_stopping,
        }

        model = xgb.XGBClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        self._model = model
        train_score = float(model.score(X_train, y_train))
        val_score   = float(model.score(X_val, y_val))
        best_iter   = model.best_iteration if hasattr(model, "best_iteration") else -1

        logger.info(
            "XGBoost trained: train=%.4f val=%.4f best_iter=%d",
            train_score, val_score, best_iter,
        )
        return TrainingResult(
            model          = model,
            feature_names  = self._feature_names,
            train_score    = train_score,
            val_score      = val_score,
            n_estimators   = self.config.n_estimators,
            best_iteration = best_iter,
        )

    def predict(self, X: Any) -> Any:
        if self._model is None:
            raise RuntimeError("Model not trained yet")
        return self._model.predict_proba(X)[:, 1]

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            return {}
        imp = self._model.feature_importances_
        return dict(zip(self._feature_names, imp.tolist()))
