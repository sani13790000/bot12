"""
XGBoost Trainer — Phase R Fix
BUG-R1: Removed internal DatasetBuilder (12 hardcoded features).
Now imports from backend.ai_prediction.dataset_builder (38 features via FeaturePipeline).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrainResult:
    accuracy:  float
    precision: float
    recall:    float
    f1:        float
    n_samples: int
    model_path: Optional[str] = None
    feature_names: List[str] = field(default_factory=list)
    auc_roc:   float = 0.0


# BUG-R1 FIX: Internal DatasetBuilder with 12 hardcoded columns REMOVED.
# train_latest() imports from backend.ai_prediction.dataset_builder
# which delegates to FeaturePipeline.feature_names() -> 38 features.


class XGBoostTrainer:
    """Trains an XGBoost classifier to predict trade profitability."""

    DEFAULT_PARAMS: Dict[str, Any] = {
        "n_estimators":        200,
        "max_depth":           6,
        "learning_rate":       0.05,
        "subsample":           0.8,
        "colsample_bytree":    0.8,
        "use_label_encoder":   False,
        "eval_metric":         "logloss",
        "random_state":        42,
        "n_jobs":              -1,
    }

    def __init__(
        self,
        model_dir: str = "/app/models/xgboost",
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._model_dir = model_dir
        self._params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._model: Optional[Any] = None
        self._feature_names: List[str] = []
        self._model_loaded: bool = False

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val:   Optional[np.ndarray] = None,
        y_val:   Optional[np.ndarray] = None,
    ) -> TrainResult:
        """Train XGBoost classifier and return evaluation metrics."""
        try:
            from xgboost import XGBClassifier
        except ImportError:
            logger.error("[XGBoostTrainer] xgboost not installed")
            return TrainResult(accuracy=0, precision=0, recall=0, f1=0, n_samples=0)

        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

        model = XGBClassifier(**self._params)
        eval_set = [(X_val, y_val)] if X_val is not None else []
        fit_kwargs: Dict[str, Any] = {}
        if eval_set:
            fit_kwargs["eval_set"] = eval_set
            fit_kwargs["verbose"] = False

        model.fit(X_train, y_train, **fit_kwargs)
        self._model = model
        self._model_loaded = True

        y_pred = model.predict(X_train)
        return TrainResult(
            accuracy=float(accuracy_score(y_train, y_pred)),
            precision=float(precision_score(y_train, y_pred, zero_division=0)),
            recall=float(recall_score(y_train, y_pred, zero_division=0)),
            f1=float(f1_score(y_train, y_pred, zero_division=0)),
            n_samples=len(y_train),
        )

    async def train_latest(
        self,
        symbol: Optional[str] = None,
        lookback_days: int = 90,
    ) -> TrainResult:
        """
        BUG-R1 FIX: import DatasetBuilder from dataset_builder.py (38 features).
        Previously used internal class with 12 hardcoded columns -> ValueError.
        """
        from backend.ai_prediction.dataset_builder import DatasetBuilder

        builder = DatasetBuilder()
        df = await builder.build(symbol=symbol, days=lookback_days)

        if df is None or len(df) < 50:
            logger.warning(
                "[XGBoostTrainer] Insufficient data (%s rows) — synthetic fallback",
                len(df) if df is not None else 0,
            )
            return await self._train_synthetic()

        feature_cols = builder.feature_names
        X = df[feature_cols].values.astype(np.float32)
        y = df["label"].values.astype(np.int32)
        self._feature_names = feature_cols

        logger.info(
            "[XGBoostTrainer] Training on %d samples x %d features",
            len(y), X.shape[1],
        )
        result = self.train(X, y)
        result.feature_names = feature_cols

        try:
            from backend.ai_prediction.model_manager import ModelManager
            mm = ModelManager(model_dir=self._model_dir)
            sym = symbol or "ALL"
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(
                None, mm.save, self._model, sym, result.auc_roc
            )
            result.model_path = str(path)
        except Exception as exc:
            logger.warning("[XGBoostTrainer] ModelManager save failed: %s", exc)

        return result

    async def _train_synthetic(self) -> TrainResult:
        """Fallback synthetic training."""
        try:
            from backend.ai_prediction.feature_pipeline import FeaturePipeline
            feature_names = FeaturePipeline.feature_names()
        except Exception:
            feature_names = [f"feature_{i}" for i in range(38)]

        rng = np.random.default_rng(42)
        n = 500
        X = rng.standard_normal((n, len(feature_names))).astype(np.float32)
        y = (rng.random(n) > 0.45).astype(np.int32)
        self._feature_names = feature_names
        result = self.train(X, y)
        result.feature_names = feature_names
        return result

    def save_model(self, path: Optional[str] = None) -> str:
        import os, pickle
        if self._model is None:
            raise RuntimeError("No model trained yet")
        save_path = path or f"{self._model_dir}/xgboost_latest.pkl"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            pickle.dump(self._model, f)
        return save_path

    def load_model(self, path: Optional[str] = None) -> None:
        import pickle
        load_path = path or f"{self._model_dir}/xgboost_latest.pkl"
        with open(load_path, "rb") as f:
            self._model = pickle.load(f)
        self._model_loaded = True

    def is_model_loaded(self) -> bool:
        return self._model_loaded and self._model is not None

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model not loaded")
        return self._model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model not loaded")
        return self._model.predict(X)

    @property
    def feature_names(self) -> List[str]:
        if self._feature_names:
            return self._feature_names
        try:
            from backend.ai_prediction.feature_pipeline import FeaturePipeline
            return FeaturePipeline.feature_names()
        except Exception:
            return []

    @property
    def model(self) -> Optional[Any]:
        return self._model
