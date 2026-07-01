"""
backend/intelligence/ml_engine.py
Galaxy Vast AI — ML Inference Engine

Provides a unified interface to run predictions using the active model.
Supports both synchronous and async inference paths.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MLEngine:
    """Lightweight ML inference wrapper."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._model_path = model_path or os.getenv("ML_MODEL_PATH", "models/active.pkl")
        self._model: Optional[Any] = None
        self._log = logging.getLogger(self.__class__.__name__)

    def load(self) -> None:
        """Load the model from disk."""
        import pickle
        try:
            with open(self._model_path, "rb") as fh:
                self._model = pickle.load(fh)
            self._log.info("Model loaded from %s", self._model_path)
        except FileNotFoundError:
            self._log.warning("Model not found at %s; using null model", self._model_path)

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Run inference. Returns prediction dict."""
        if self._model is None:
            return {"signal": "HOLD", "confidence": 0.0, "model": "null"}
        try:
            import numpy as np
            feat_vec = list(features.values())
            arr = np.array(feat_vec).reshape(1, -1)
            proba = self._model.predict_proba(arr)[0]
            confidence = float(max(proba))
            label = int(self._model.predict(arr)[0])
            return {
                "signal": "BUY" if label == 1 else "SELL" if label == -1 else "HOLD",
                "confidence": confidence,
                "label": label,
                "model": self._model_path,
            }
        except Exception as exc:
            self._log.error("Prediction error: %s", exc)
            return {"signal": "HOLD", "confidence": 0.0, "error": str(exc)}

    async def async_predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Async wrapper around predict."""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.predict, features)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


_engine: Optional[MLEngine] = None


def get_ml_engine() -> MLEngine:
    global _engine
    if _engine is None:
        _engine = MLEngine()
    return _engine
