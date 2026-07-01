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
_CACHE: Dict[str, Any] = {}
_CACHE_MAX = int(os.getenv("MODEL_CACHE_SIZE", "5"))


@dataclass
class ModelVersion:
    version_id: str
    created_at: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    path: Optional[str] = None
    is_active: bool = False


@dataclass
class DriftReport:
    detected: bool
    score: float
    threshold: float
    features_drifted: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ModelManager:
    """Versioned ML model manager with LRU cache and drift detection."""

    def __init__(self, model_dir: str = "models", drift_threshold: float = 0.15) -> None:
        self._model_dir = model_dir
        self._drift_threshold = drift_threshold
        self._versions: Dict[str, ModelVersion] = {}
        self._active: Optional[str] = None
        self._lock = asyncio.Lock()
        self._log = logging.getLogger(self.__class__.__name__)

    async def load(self, version_id: str) -> Any:
        """Load model version into LRU cache."""
        if version_id in _CACHE:
            self._log.debug("Cache hit: %s", version_id)
            return _CACHE[version_id]
        path = os.path.join(self._model_dir, f"{version_id}.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path}")
        async with self._lock:
            with open(path, "rb") as fh:
                model = pickle.load(fh)
            if len(_CACHE) >= _CACHE_MAX:
                oldest = next(iter(_CACHE))
                del _CACHE[oldest]
            _CACHE[version_id] = model
            self._log.info("Loaded model %s", version_id)
            return model

    async def save(self, version_id: str, model: Any, metrics: Optional[Dict[str, float]] = None) -> ModelVersion:
        """Persist model and register version."""
        os.makedirs(self._model_dir, exist_ok=True)
        path = os.path.join(self._model_dir, f"{version_id}.pkl")
        async with self._lock:
            with open(path, "wb") as fh:
                pickle.dump(model, fh)
            ver = ModelVersion(
                version_id=version_id,
                created_at=datetime.now(timezone.utc),
                metrics=metrics or {},
                path=path,
            )
            self._versions[version_id] = ver
            _CACHE[version_id] = model
            self._log.info("Saved model %s metrics=%s", version_id, metrics)
            return ver

    async def promote(self, version_id: str) -> None:
        """Promote a version to active."""
        async with self._lock:
            if version_id not in self._versions:
                raise KeyError(f"Unknown version: {version_id}")
            if self._active:
                self._versions[self._active].is_active = False
            self._versions[version_id].is_active = True
            self._active = version_id
            self._log.info("Promoted %s to active", version_id)

    async def detect_drift(self, reference_stats: Dict[str, float], current_stats: Dict[str, float]) -> DriftReport:
        """Simple PSI-based drift detection."""
        drifted = []
        total_score = 0.0
        for feat, ref_val in reference_stats.items():
            cur_val = current_stats.get(feat, ref_val)
            if ref_val == 0:
                continue
            psi = abs(cur_val - ref_val) / (ref_val + 1e-9)
            total_score += psi
            if psi > self._drift_threshold:
                drifted.append(feat)
        avg_score = total_score / max(len(reference_stats), 1)
        return DriftReport(
            detected=avg_score > self._drift_threshold,
            score=avg_score,
            threshold=self._drift_threshold,
            features_drifted=drifted,
        )

    def list_versions(self) -> List[ModelVersion]:
        return list(self._versions.values())

    @property
    def active_version(self) -> Optional[str]:
        return self._active


_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
