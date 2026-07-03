"""
backend/ai_prediction/model_manager.py
Galaxy Vast AI -- ML Model Manager

Manages XGBoost and other ML models: training, versioning, loading.
"""
from __future__ import annotations

import logging
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/tmp/models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class ModelVersion:
    """Represents a saved model version."""

    def __init__(self, name: str, version: int, model: Any, metrics: dict) -> None:
        self.name = name
        self.version = version
        self.model = model
        self.metrics = metrics
        self.created_at = datetime.now(timezone.utc).isoformat()

    def save(self) -> Path:
        path = MODEL_DIR / f"{self.name}_v{self.version}.pkl"
        with open(path, "wb") as fh:
            pickle.dump(self, fh)
        logger.info("Saved model %s v%d to %s", self.name, self.version, path)
        return path

    @classmethod
    def load(cls, path: Path) -> "ModelVersion":
        with open(path, "rb") as fh:
            return pickle.load(fh)


class ModelManager:
    """Registry and lifecycle manager for ML models."""

    def __init__(self) -> None:
        self._registry: dict[str, list[ModelVersion]] = {}

    def register(self, name: str, model: Any, metrics: dict) -> ModelVersion:
        versions = self._registry.setdefault(name, [])
        version = len(versions) + 1
        mv = ModelVersion(name, version, model, metrics)
        versions.append(mv)
        mv.save()
        return mv

    def latest(self, name: str) -> Optional[ModelVersion]:
        versions = self._registry.get(name, [])
        return versions[-1] if versions else None

    def list_versions(self, name: str) -> list[dict]:
        return [
            {"version": mv.version, "metrics": mv.metrics, "created_at": mv.created_at}
            for mv in self._registry.get(name, [])
        ]

    def load_from_disk(self, name: str) -> Optional[ModelVersion]:
        candidates = sorted(MODEL_DIR.glob(f"{name}_v*.pkl"))
        if not candidates:
            return None
        mv = ModelVersion.load(candidates[-1])
        self._registry.setdefault(name, []).append(mv)
        return mv


model_manager = ModelManager()
