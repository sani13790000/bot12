"""
backend/ai_prediction/model_manager.py
Galaxy Vast AI — ML Model Manager

Manages versioned ML models: load, save, version tracking, hot-swap.
Supports XGBoost and scikit-learn compatible models.
"""
from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_DIR = Path(os.getenv("MODEL_DIR", "/tmp/galaxy_models"))


@dataclass
class ModelVersion:
    """Metadata for a saved model version."""
    version:    str
    model_type: str
    path:       Path
    metrics:    Dict[str, float] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_active:  bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version":    self.version,
            "model_type": self.model_type,
            "path":       str(self.path),
            "metrics":    self.metrics,
            "created_at": self.created_at,
            "is_active":  self.is_active,
        }


class ModelManager:
    """
    Manages ML model lifecycle: save, load, version, hot-swap.

    Usage::

        mm = ModelManager()
        mm.save_model(model, "xgboost", {"accuracy": 0.87})
        loaded = mm.load_active("xgboost")
    """

    def __init__(self, model_dir: Optional[Path] = None) -> None:
        self._dir = model_dir or _DEFAULT_MODEL_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, List[ModelVersion]] = {}
        logger.info("[ModelManager] model dir: %s", self._dir)

    # ------------------------------------------------------------------ #
    # Save / Load
    # ------------------------------------------------------------------ #

    def save_model(
        self,
        model:      Any,
        model_type: str,
        metrics:    Optional[Dict[str, float]] = None,
    ) -> ModelVersion:
        """Pickle a model and register it as the new active version."""
        import time
        version = f"{model_type}_{int(time.time())}"
        path = self._dir / f"{version}.pkl"
        with open(path, "wb") as fh:
            pickle.dump(model, fh)
        mv = ModelVersion(
            version=version,
            model_type=model_type,
            path=path,
            metrics=metrics or {},
            is_active=True,
        )
        # deactivate old active
        for old in self._versions.get(model_type, []):
            old.is_active = False
        self._versions.setdefault(model_type, []).append(mv)
        logger.info("[ModelManager] saved %s v=%s metrics=%s", model_type, version, metrics)
        return mv

    def load_active(self, model_type: str) -> Optional[Any]:
        """Load the currently active model for model_type."""
        versions = self._versions.get(model_type, [])
        active = next((v for v in reversed(versions) if v.is_active), None)
        if active is None:
            logger.warning("[ModelManager] no active model for '%s'", model_type)
            return None
        if not active.path.exists():
            logger.error("[ModelManager] model file missing: %s", active.path)
            return None
        with open(active.path, "rb") as fh:
            model = pickle.load(fh)
        logger.debug("[ModelManager] loaded %s v=%s", model_type, active.version)
        return model

    # ------------------------------------------------------------------ #
    # Version management
    # ------------------------------------------------------------------ #

    def list_versions(self, model_type: str) -> List[Dict[str, Any]]:
        """List all versions for a model type."""
        return [v.to_dict() for v in self._versions.get(model_type, [])]

    def rollback(self, model_type: str, version: str) -> bool:
        """Set a specific version as active."""
        versions = self._versions.get(model_type, [])
        target = next((v for v in versions if v.version == version), None)
        if target is None:
            logger.warning("[ModelManager] rollback: version not found: %s", version)
            return False
        for v in versions:
            v.is_active = False
        target.is_active = True
        logger.info("[ModelManager] rolled back %s to v=%s", model_type, version)
        return True


# Module-level singleton
model_manager = ModelManager()
