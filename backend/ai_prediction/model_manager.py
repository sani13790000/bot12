"""
ModelManager v2 — Phase G Fix

Fixes:
- BUG-G3: load_best_model() now scans /app/models/xgboost/ directory
- BUG-G5: Model versioning with manifest file (best_model.json)
- NEW: get_best_metadata() returns AUC and n_samples for confidence calculation
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MODEL_DIR = os.environ.get("MODEL_DIR", "/app/models/xgboost")
_MANIFEST_FILE = "best_model.json"


@dataclass
class ModelMetadata:
    """Metadata stored alongside each trained model."""
    symbol:       str
    trained_at:   str
    n_samples:    int
    accuracy:     float
    precision:    float
    recall:       float
    f1:           float
    auc_roc:      float = 0.60
    model_path:   str = ""
    feature_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol":        self.symbol,
            "trained_at":    self.trained_at,
            "n_samples":     self.n_samples,
            "accuracy":      round(self.accuracy, 4),
            "precision":     round(self.precision, 4),
            "recall":        round(self.recall, 4),
            "f1":            round(self.f1, 4),
            "auc_roc":       round(self.auc_roc, 4),
            "model_path":    self.model_path,
            "feature_names": self.feature_names,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelMetadata":
        return cls(
            symbol=d.get("symbol", "UNKNOWN"),
            trained_at=d.get("trained_at", ""),
            n_samples=d.get("n_samples", 0),
            accuracy=d.get("accuracy", 0.0),
            precision=d.get("precision", 0.0),
            recall=d.get("recall", 0.0),
            f1=d.get("f1", 0.0),
            auc_roc=d.get("auc_roc", 0.60),
            model_path=d.get("model_path", ""),
            feature_names=d.get("feature_names", []),
        )


class ModelManager:
    """
    Phase G: versioned model storage.
    - Saves model_<timestamp>.pkl + updates best_model.json manifest
    - load_best_model(symbol) returns the highest-AUC model for that symbol
    - Falls back to latest model if no per-symbol model exists
    """

    def __init__(self, model_dir: str = _MODEL_DIR) -> None:
        self._model_dir = model_dir
        os.makedirs(self._model_dir, exist_ok=True)

    # ── Saving ────────────────────────────────────────────────────────────────

    def save_model(
        self,
        model: Any,
        meta: ModelMetadata,
    ) -> str:
        """Persist model + metadata. Returns saved path."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"model_{meta.symbol}_{ts}.pkl"
        path = os.path.join(self._model_dir, filename)
        obj = {"model": model, "metadata": meta.to_dict()}
        with open(path, "wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
        meta.model_path = path
        logger.info("[ModelManager] saved %s (auc=%.3f n=%d)", path, meta.auc_roc, meta.n_samples)

        # Update manifest
        self._update_manifest(meta)
        return path

    def _update_manifest(self, meta: ModelMetadata) -> None:
        """Update best_model.json: keep only the entry per symbol with highest AUC."""
        manifest_path = os.path.join(self._model_dir, _MANIFEST_FILE)
        try:
            if os.path.exists(manifest_path):
                with open(manifest_path, "r") as fh:
                    manifest: Dict[str, Any] = json.load(fh)
            else:
                manifest = {}

            key = meta.symbol
            existing = manifest.get(key)
            if existing is None or meta.auc_roc >= existing.get("auc_roc", 0.0):
                manifest[key] = meta.to_dict()
                with open(manifest_path, "w") as fh:
                    json.dump(manifest, fh, indent=2)
                logger.info("[ModelManager] manifest updated for %s (auc=%.3f)", key, meta.auc_roc)
        except Exception as exc:
            logger.warning("[ModelManager] manifest update failed: %s", exc)

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_best_model(self, symbol: str = "default") -> Optional[Any]:
        """
        BUG-G3 FIX: Load best model for given symbol.
        1. Check manifest for symbol-specific best model
        2. Fall back to any model in directory
        3. Return None if no model found
        """
        # Try manifest first
        manifest_path = os.path.join(self._model_dir, _MANIFEST_FILE)
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as fh:
                    manifest = json.load(fh)
                entry = manifest.get(symbol) or manifest.get("default") or next(iter(manifest.values()), None)
                if entry and entry.get("model_path") and os.path.exists(entry["model_path"]):
                    return self._load_pkl(entry["model_path"])
            except Exception as exc:
                logger.warning("[ModelManager] manifest read failed: %s", exc)

        # Fallback: scan directory for latest pkl
        return self._load_latest_pkl()

    def get_best_metadata(self, symbol: str = "default") -> Optional[ModelMetadata]:
        """Return metadata for best model of given symbol."""
        manifest_path = os.path.join(self._model_dir, _MANIFEST_FILE)
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r") as fh:
                manifest = json.load(fh)
            entry = manifest.get(symbol) or manifest.get("default") or next(iter(manifest.values()), None)
            return ModelMetadata.from_dict(entry) if entry else None
        except Exception as exc:
            logger.warning("[ModelManager] metadata read failed: %s", exc)
            return None

    def _load_pkl(self, path: str) -> Optional[Any]:
        try:
            with open(path, "rb") as fh:
                obj = pickle.load(fh)
            model = obj.get("model") if isinstance(obj, dict) else obj
            logger.info("[ModelManager] loaded model from %s", path)
            return model
        except Exception as exc:
            logger.error("[ModelManager] failed to load %s: %s", path, exc)
            return None

    def _load_latest_pkl(self) -> Optional[Any]:
        """Load most recently modified .pkl file in model_dir."""
        try:
            pkls = [
                os.path.join(self._model_dir, f)
                for f in os.listdir(self._model_dir)
                if f.endswith(".pkl")
            ]
            if not pkls:
                logger.info("[ModelManager] no .pkl files in %s", self._model_dir)
                return None
            latest = max(pkls, key=os.path.getmtime)
            return self._load_pkl(latest)
        except Exception as exc:
            logger.warning("[ModelManager] directory scan failed: %s", exc)
            return None

    def list_models(self) -> List[ModelMetadata]:
        """List all models from manifest."""
        manifest_path = os.path.join(self._model_dir, _MANIFEST_FILE)
        if not os.path.exists(manifest_path):
            return []
        try:
            with open(manifest_path, "r") as fh:
                manifest = json.load(fh)
            return [ModelMetadata.from_dict(v) for v in manifest.values()]
        except Exception:
            return []
