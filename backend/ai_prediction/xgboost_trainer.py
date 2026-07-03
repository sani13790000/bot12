from __future__ import annotations
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from ..core.logger import get_logger

logger = get_logger('ai_prediction.xgboost_trainer')


class XGBoostTrainer:
    """XGBoost model trainer for trading signal prediction."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self._params = params or {
            'n_estimators':    200,
            'max_depth':       6,
            'learning_rate':   0.05,
            'subsample':       0.8,
            'colsample_bytree': 0.8,
            'use_label_encoder': False,
            'eval_metric':     'logloss',
            'random_state':    42,
        }
        self._model = None
        self._log   = logger
        self._feature_names: List[str] = []

    def _import_deps(self):
        try:
            import xgboost as xgb
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            return xgb, train_test_split, accuracy_score, precision_score, recall_score, f1_score
        except ImportError as e:
            raise ImportError(f'required package missing: {e}; run: pip install xgboost scikit-learn') from e

    def train(self, X, y, feature_names: Optional[List[str]] = None):
        xgb, train_test_split, accuracy_score, *_ = self._import_deps()
        t_start = time.perf_counter()

        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        self._model = xgb.XGBClassifier(**self._params)
        self._model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        self._feature_names = feature_names or [f'f{i}' for i in range(X.shape[1])]

        preds = self._model.predict(X_val)
        acc   = accuracy_score(y_val, preds)
        t_elapsed = time.perf_counter() - t_start

        self._log.info('XGBoost trained: acc=%.4f elapsed=%.2fs samples=%d', acc, t_elapsed, len(X))
        return {'accuracy': acc, 'elapsed_s': t_elapsed, 'n_train': len(X_train), 'n_val': len(X_val)}

    def predict(self, X):
        if self._model is None:
            raise RuntimeError('Model not trained. Call train() first.')
        return self._model.predict(X)

    def predict_proba(self, X):
        if self._model is None:
            raise RuntimeError('Model not trained. Call train() first.')
        return self._model.predict_proba(X)

    def feature_importance(self) -> Dict[str, float]:
        if self._model is None:
            return {}
        scores = self._model.feature_importances_
        return dict(zip(self._feature_names, scores.tolist()))

    def save(self, path: str) -> None:
        if self._model is None:
            raise RuntimeError('No model to save')
        self._model.save_model(path)
        self._log.info('XGBoost model saved to %s', path)

    def load(self, path: str) -> None:
        xgb, *_ = self._import_deps()
        self._model = xgb.XGBClassifier()
        self._model.load_model(path)
        self._log.info('XGBoost model loaded from %s', path)
