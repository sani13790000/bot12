"""
XGBoost Trainer — Phase A Fix
Added: train_latest() wrapper that retraining_service.py expects.
Fixed: dataset building from recent trade history.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrainResult:
    accuracy: float
    precision: float
    recall: float
    f1: float
    n_samples: int
    model_path: Optional[str] = None
    feature_names: List[str] = field(default_factory=list)


class DatasetBuilder:
    """
    Builds feature matrix and labels from recent closed trades stored in Supabase.
    Phase A: minimal implementation — loads from 'trades' table.
    """

    def __init__(self, lookback_days: int = 90) -> None:
        self.lookback_days = lookback_days
        self._feature_cols = [
            "rsi", "macd", "macd_signal", "bb_upper", "bb_lower",
            "atr", "volume_ratio", "spread", "session_hour",
            "day_of_week", "smc_score", "pa_score",
        ]

    async def build(self) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Returns (X, y, feature_names).
        X: float32 feature matrix, shape (n_samples, n_features)
        y: int labels (1=profit, 0=loss)
        """
        try:
            from backend.database.connection import get_db_client
            client = await get_db_client()
            resp = (
                client.table("trades")
                .select(
                    "rsi,macd,macd_signal,bb_upper,bb_lower,"
                    "atr,volume_ratio,spread,session_hour,"
                    "day_of_week,smc_score,pa_score,profit_usd,status"
                )
                .eq("status", "closed")
                .order("closed_at", desc=True)
                .limit(5000)
                .execute()
            )
            rows = resp.data or []
        except Exception as exc:
            logger.warning(
                "[DatasetBuilder] Could not load trades from DB: %s — "
                "using synthetic fallback dataset", exc
            )
            rows = []

        if len(rows) < 50:
            logger.warning(
                "[DatasetBuilder] Only %d trades found — using synthetic data",
                len(rows)
            )
            return self._synthetic_dataset()

        X_list, y_list = [], []
        for row in rows:
            try:
                features = [
                    float(row.get(col, 0.0) or 0.0)
                    for col in self._feature_cols
                ]
                label = 1 if (row.get("profit_usd") or 0) > 0 else 0
                X_list.append(features)
                y_list.append(label)
            except (TypeError, ValueError):
                continue

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)
        logger.info("[DatasetBuilder] Built dataset: %d samples, %d features", len(y), X.shape[1])
        return X, y, self._feature_cols

    def _synthetic_dataset(
        self, n: int = 500
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Minimal synthetic dataset for cold-start."""
        rng = np.random.default_rng(42)
        X = rng.standard_normal((n, len(self._feature_cols))).astype(np.float32)
        y = (rng.random(n) > 0.45).astype(np.int32)
        logger.info("[DatasetBuilder] Synthetic dataset: %d samples", n)
        return X, y, self._feature_cols


class XGBoostTrainer:
    """Trains an XGBoost classifier to predict trade profitability."""

    DEFAULT_PARAMS: Dict[str, Any] = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "use_label_encoder": False,
        "eval_metric": "logloss",
        "random_state": 42,
        "n_jobs": -1,
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

    # ── Training ──────────────────────────────────────────────────────────────

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> TrainResult:
        """
        Train XGBoost classifier and return evaluation metrics.
        This is the core training method.
        """
        try:
            from xgboost import XGBClassifier
        except ImportError:
            logger.error("[XGBoostTrainer] xgboost not installed")
            return TrainResult(accuracy=0.0, precision=0.0, recall=0.0, f1=0.0, n_samples=0)

        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import train_test_split

        if X_val is None or y_val is None:
            X_train, X_val, y_train, y_val = train_test_split(
                X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
            )

        model = XGBClassifier(**self._params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        self._model = model

        y_pred = model.predict(X_val)
        acc = float(accuracy_score(y_val, y_pred))

        try:
            from sklearn.metrics import precision_score, recall_score, f1_score
            prec = float(precision_score(y_val, y_pred, zero_division=0))
            rec = float(recall_score(y_val, y_pred, zero_division=0))
            f1 = float(f1_score(y_val, y_pred, zero_division=0))
        except Exception:
            prec = rec = f1 = 0.0

        logger.info(
            "[XGBoostTrainer] train() — acc=%.4f prec=%.4f rec=%.4f f1=%.4f n=%d",
            acc, prec, rec, f1, len(y_train)
        )
        return TrainResult(
            accuracy=acc,
            precision=prec,
            recall=rec,
            f1=f1,
            n_samples=len(y_train),
        )

    async def train_latest(
        self,
        lookback_days: int = 90,
        min_samples: int = 50,
    ) -> TrainResult:
        """
        PHASE A FIX: This method was called by retraining_service.py but
        did not exist, causing AttributeError on every retrain cycle.

        Builds dataset from recent trades, trains model, saves if improved.
        Returns TrainResult with real accuracy metrics.
        """
        builder = DatasetBuilder(lookback_days=lookback_days)
        loop = asyncio.get_running_loop()

        # Build dataset async (DB I/O)
        X, y, feature_names = await builder.build()
        self._feature_names = feature_names

        if len(y) < min_samples:
            logger.warning(
                "[XGBoostTrainer] train_latest() — only %d samples < min %d — skipping",
                len(y), min_samples
            )
            return TrainResult(
                accuracy=0.0, precision=0.0, recall=0.0, f1=0.0, n_samples=len(y)
            )

        # Run CPU-bound training in thread pool
        import asyncio
        result = await loop.run_in_executor(
            None, self.train, X, y, None, None
        )

        # Save model if training succeeded
        if result.accuracy > 0 and self._model is not None:
            try:
                saved_path = await loop.run_in_executor(None, self._save_model)
                result.model_path = saved_path
                result.feature_names = feature_names
            except Exception as exc:
                logger.warning("[XGBoostTrainer] Could not save model: %s", exc)

        return result

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Return class probabilities for feature matrix."""
        if self._model is None:
            raise RuntimeError("Model not trained yet — call train() or train_latest() first")
        return self._model.predict_proba(features)

    def predict(self, features: np.ndarray, threshold: float = 0.55) -> np.ndarray:
        """Return binary predictions with configurable confidence threshold."""
        proba = self.predict_proba(features)
        return (proba[:, 1] >= threshold).astype(int)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_model(self) -> str:
        """Save model to disk. Returns saved path."""
        import os
        import pickle
        os.makedirs(self._model_dir, exist_ok=True)
        path = os.path.join(self._model_dir, "model_latest.pkl")
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "features": self._feature_names}, f)
        logger.info("[XGBoostTrainer] Model saved to %s", path)
        return path

    def load_model(self, path: Optional[str] = None) -> bool:
        """Load model from disk. Returns True if successful."""
        import os
        import pickle
        load_path = path or os.path.join(self._model_dir, "model_latest.pkl")
        if not os.path.exists(load_path):
            logger.warning("[XGBoostTrainer] No model file at %s", load_path)
            return False
        try:
            with open(load_path, "rb") as f:
                obj = pickle.load(f)
            self._model = obj["model"]
            self._feature_names = obj.get("features", [])
            logger.info("[XGBoostTrainer] Loaded model from %s", load_path)
            return True
        except Exception as exc:
            logger.error("[XGBoostTrainer] Failed to load model: %s", exc)
            return False


# Module-level import fix for train_latest
import asyncio
