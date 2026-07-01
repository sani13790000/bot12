"""
backend/ai_prediction/model_manager.py
Galaxy Vast AI — ML Model Manager

Manages versioned ML models with LRU cache and drift detection.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    version: str
    symbol: str
    model_type: str
    accuracy: float = 0.0
    created_at: float = field(default_factory=time.time)
    is_active: bool = False


class ModelManager:
    """Manages ML model versions with LRU caching."""

    def __init__(self, cache_size: int = 10) -> None:
        self._models: Dict[str, ModelVersion] = {}
        self._cache_size = cache_size

    def register(self, version: ModelVersion) -> None:
        self._models[version.version] = version

    def get_active(self, symbol: str) -> Optional[ModelVersion]:
        for v in self._models.values():
            if v.symbol == symbol and v.is_active:
                return v
        return None

    def activate(self, version_id: str) -> bool:
        if version_id not in self._models:
            return False
        symbol = self._models[version_id].symbol
        for v in self._models.values():
            if v.symbol == symbol:
                v.is_active = False
        self._models[version_id].is_active = True
        return True

    def list_versions(self, symbol: Optional[str] = None) -> List[ModelVersion]:
        versions = list(self._models.values())
        if symbol:
            versions = [v for v in versions if v.symbol == symbol]
        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def detect_drift(self, symbol: str, recent_accuracy: float) -> bool:
        active = self.get_active(symbol)
        if not active:
            return False
        drift = abs(active.accuracy - recent_accuracy) > 0.1
        if drift:
            _LOG.warning('Model drift detected for %s: %.2f -> %.2f', symbol, active.accuracy, recent_accuracy)
        return drift


_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
