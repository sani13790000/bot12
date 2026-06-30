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
    """A registered model version."""

    name: str
    version: int
    path: str
    metrics: Dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ModelManager:
    """Async model registry with simple in-memory cache."""

    def __init__(self, model_dir: Optional[str] = None) -> None:
        self.model_dir = model_dir or os.getenv("MODEL_DIR", "./models")
        os.makedirs(self.model_dir, exist_ok=True)
        self._models: Dict[str, ModelVersion] = {}
        self._cache: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        name: str,
        model: Any,
        metrics: Optional[Dict[str, float]] = None,
    ) -> ModelVersion:
        async with self._lock:
            version = len(self._models) + 1
            filename = f"{name}_v{version}.pkl"
            path = os.path.join(self.model_dir, filename)
            await asyncio.to_thread(self._save, model, path)
            mv = ModelVersion(
                name=name,
                version=version,
                path=path,
                metrics=metrics or {},
            )
            self._models[name] = mv
            self._cache[name] = model
            _LOG.info("Registered model %s v%d at %s", name, version, path)
            return mv

    async def load(self, name: str) -> Any:
        async with self._lock:
            if name in self._cache:
                return self._cache[name]
            mv = self._models.get(name)
            if not mv or not os.path.exists(mv.path):
                raise FileNotFoundError(f"Model {name} not found")
            model = await asyncio.to_thread(self._load, mv.path)
            self._cache[name] = model
            return model

    async def list_models(self) -> List[ModelVersion]:
        async with self._lock:
            return list(self._models.values())

    async def latest(self, name: str) -> Optional[ModelVersion]:
        async with self._lock:
            return self._models.get(name)

    def _save(self, model: Any, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(model, f)

    def _load(self, path: str) -> Any:
        with open(path, "rb") as f:
            return pickle.load(f)

    async def detect_drift(
        self,
        name: str,
        recent_metric: float,
        threshold: float = 0.1,
    ) -> bool:
        mv = await self.latest(name)
        if not mv or not mv.metrics:
            return False
        baseline = mv.metrics.get("accuracy", 0.0)
        drift = abs(baseline - recent_metric)
        _LOG.info("Drift check for %s: baseline=%.4f recent=%.4f drift=%.4f", name, baseline, recent_metric, drift)
        return drift > threshold
