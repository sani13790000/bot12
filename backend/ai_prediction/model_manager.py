"""
backend/ai_prediction/model_manager.py
Galaxy Vast AI — ML Model Manager

Manages versioned ML models for signal generation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    model_id: str
    version: str
    created_at: float = field(default_factory=time.time)
    metrics: dict[str, Any] = field(default_factory=dict)
    path: str = ""
    is_active: bool = False


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelMetadata] = {}
        self._active: str | None = None

    def register(self, meta: ModelMetadata) -> None:
        self._models[meta.model_id] = meta
        logger.info("Registered model %s v%s", meta.model_id, meta.version)

    def activate(self, model_id: str) -> None:
        if model_id not in self._models:
            raise KeyError(f"Model {model_id!r} not found")
        self._active = model_id
        self._models[model_id].is_active = True
        logger.info("Activated model %s", model_id)

    def get_active(self) -> ModelMetadata | None:
        if self._active:
            return self._models.get(self._active)
        return None

    def list_models(self) -> list[ModelMetadata]:
        return list(self._models.values())

    def deactivate(self, model_id: str) -> None:
        if model_id in self._models:
            self._models[model_id].is_active = False
        if self._active == model_id:
            self._active = None


class ModelManager:
    """High-level manager: load, score, version ML models."""

    def __init__(self, model_dir: str = "models") -> None:
        self.model_dir = Path(model_dir)
        self.registry = ModelRegistry()
        logger.info("ModelManager initialized with dir=%s", model_dir)

    def load_model(self, model_id: str, version: str, path: str) -> ModelMetadata:
        meta = ModelMetadata(model_id=model_id, version=version, path=path)
        self.registry.register(meta)
        return meta

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        active = self.registry.get_active()
        if not active:
            raise RuntimeError("No active model")
        logger.debug("Predicting with model %s", active.model_id)
        # Stub: real implementation loads model from active.path
        return {"signal": "HOLD", "confidence": 0.5, "model_id": active.model_id}

    def score_model(self, model_id: str, metrics: dict[str, float]) -> None:
        if model_id in self.registry._models:
            self.registry._models[model_id].metrics.update(metrics)


__all__ = ["ModelManager", "ModelMetadata", "ModelRegistry"]
