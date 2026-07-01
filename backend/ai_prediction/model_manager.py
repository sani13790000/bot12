"""
backend/ai_prediction/model_manager.py
Galaxy Vast AI — ML Model Manager

Manages versioned ML models with LRU cache and drift detection.
"""
from __future__ import annotations

import asyncio
import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    """Versioned model record."""
    version: str
    path: str
    accuracy: float = 0.0
    trained_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelManager:
    """Thread-safe ML model manager with LRU cache."""

    def __init__(self, model_dir: str = "models", max_cached: int = 5) -> None:
        self._dir = model_dir
        self._max_cached = max_cached
        self._cache: Dict[str, Any] = {}
        self._versions: List[ModelVersion] = []
        self._lock = asyncio.Lock()
        os.makedirs(model_dir, exist_ok=True)
        _LOG.info("ModelManager initialised — dir=%s", model_dir)

    async def save(self, model: Any, version: str, *, accuracy: float = 0.0,
                   metadata: Optional[Dict[str, Any]] = None) -> ModelVersion:
        async with self._lock:
            path = os.path.join(self._dir, f"{version}.pkl")
            with open(path, "wb") as fh:
                pickle.dump(model, fh, protocol=5)
            mv = ModelVersion(version=version, path=path, accuracy=accuracy,
                              metadata=metadata or {})
            self._versions.append(mv)
            self._cache[version] = model
            self._evict_lru()
            _LOG.info("Model saved: %s (acc=%.4f)", version, accuracy)
            return mv

    async def load(self, version: str) -> Any:
        async with self._lock:
            if version in self._cache:
                return self._cache[version]
            path = os.path.join(self._dir, f"{version}.pkl")
            if not os.path.exists(path):
                raise FileNotFoundError(f"Model version not found: {version}")
            with open(path, "rb") as fh:
                model = pickle.load(fh)
            self._cache[version] = model
            self._evict_lru()
            return model

    def list_versions(self) -> List[ModelVersion]:
        return list(self._versions)

    def latest_version(self) -> Optional[ModelVersion]:
        return self._versions[-1] if self._versions else None

    def _evict_lru(self) -> None:
        while len(self._cache) > self._max_cached:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            _LOG.debug("LRU evicted model: %s", oldest)

    async def detect_drift(self, model_version: str, new_accuracy: float,
                           threshold: float = 0.05) -> bool:
        mv = next((v for v in self._versions if v.version == model_version), None)
        if mv is None:
            return False
        drift = mv.accuracy - new_accuracy
        if drift > threshold:
            _LOG.warning("Model drift detected: %s (delta=%.4f)", model_version, drift)
            return True
        return False


_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
