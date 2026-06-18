from __future__ import annotations

import json
import os
import pickle
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger
from .xgboost_trainer import TrainingResult

logger = get_logger("ai_prediction.model_manager")


@dataclass
class ModelMetadata:
    model_id:   str
    symbol:     str
    version:    int
    file_path:  str
    trained_at: str
    auc_roc:    float
    accuracy:   float
    f1_score:   float
    n_samples:  int
    win_rate:   float
    is_best:    bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def trained_at_dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.trained_at).replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


@dataclass
class _CacheEntry:
    model:        Any
    loaded_at:    datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0


class ModelManager:
    _instance: Optional["ModelManager"] = None

    MODELS_DIR:              str = "models"
    METADATA_FILE:           str = "models/metadata.json"
    MAX_MODELS_PER_SYMBOL:   int = 5
    MAX_CACHED_MODELS:       int = 3
    DEFAULT_STALENESS_HOURS: int = 24

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        os.makedirs(self.MODELS_DIR, exist_ok=True)
        self._metadata: Dict[str, List[ModelMetadata]] = {}
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._staleness_hours = self.DEFAULT_STALENESS_HOURS
        self._load_metadata()
        self._initialized = True
        logger.info("ModelManager initialized — models_dir=%s", self.MODELS_DIR)

    def save_model(
        self,
        result:    TrainingResult,
        symbol:    str,
        n_samples: int,
        win_rate:  float,
    ) -> ModelMetadata:
        version   = self._next_version(symbol)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_id  = f"galaxy_vast_{symbol}_v{version}_{timestamp}"
        file_path = os.path.join(self.MODELS_DIR, f"{model_id}.pkl")

        with open(file_path, "wb") as f:
            pickle.dump(result.model, f, protocol=pickle.HIGHEST_PROTOCOL)

        metadata = ModelMetadata(
            model_id   = model_id,
            symbol     = symbol,
            version    = version,
            file_path  = file_path,
            trained_at = datetime.now(timezone.utc).isoformat(),
            auc_roc    = result.auc_roc,
            accuracy   = result.accuracy,
            f1_score   = result.f1_score,
            n_samples  = n_samples,
            win_rate   = win_rate,
        )

        if symbol not in self._metadata:
            self._metadata[symbol] = []
        self._metadata[symbol].append(metadata)

        self._update_best(symbol)
        self._cleanup_old_models(symbol)
        self._save_metadata()
        self.invalidate_cache(symbol)

        logger.info("model saved — %s (AUC=%.3f)", model_id, result.auc_roc)
        return metadata

    def load_best_model(self, symbol: str) -> Optional[Any]:
        if symbol in self._cache:
            entry = self._cache[symbol]
            age_hours = (
                datetime.now(timezone.utc) - entry.loaded_at
            ).total_seconds() / 3600.0
            if age_hours < self._staleness_hours:
                self._cache.move_to_end(symbol)
                entry.access_count += 1
                logger.debug(
                    "model cache hit for %s (age=%.1fh, accesses=%d)",
                    symbol, age_hours, entry.access_count,
                )
                return entry.model
            else:
                logger.info("model stale for %s (age=%.1fh) — reloading", symbol, age_hours)
                del self._cache[symbol]

        best = self._get_best_metadata(symbol)
        if best is None:
            logger.warning("no model found for symbol %s", symbol)
            return None
        if not os.path.exists(best.file_path):
            logger.error("model file not found: %s", best.file_path)
            return None

        with open(best.file_path, "rb") as f:
            model = pickle.load(f)

        self._add_to_cache(symbol, model)
        logger.info(
            "best model loaded for %s — v%d (AUC=%.3f)",
            symbol, best.version, best.auc_roc,
        )
        return model

    def get_best_metadata(self, symbol: str) -> Optional[ModelMetadata]:
        return self._get_best_metadata(symbol)

    def list_models(self, symbol: Optional[str] = None) -> List[ModelMetadata]:
        if symbol:
            return self._metadata.get(symbol, [])
        return [m for models in self._metadata.values() for m in models]

    def invalidate_cache(self, symbol: str) -> None:
        if symbol in self._cache:
            del self._cache[symbol]
            logger.debug("model cache invalidated for %s", symbol)

    def has_model(self, symbol: str) -> bool:
        return bool(self._metadata.get(symbol))

    def get_staleness_info(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        info = {}
        for symbol, entry in self._cache.items():
            age_hours = (now - entry.loaded_at).total_seconds() / 3600.0
            info[symbol] = {
                "loaded_at":    entry.loaded_at.isoformat(),
                "age_hours":    round(age_hours, 2),
                "is_stale":     age_hours >= self._staleness_hours,
                "access_count": entry.access_count,
            }
        return {
            "cached_models":   list(self._cache.keys()),
            "cache_size":      len(self._cache),
            "max_cache_size":  self.MAX_CACHED_MODELS,
            "staleness_hours": self._staleness_hours,
            "models_detail":   info,
        }

    def _add_to_cache(self, symbol: str, model: Any) -> None:
        while len(self._cache) >= self.MAX_CACHED_MODELS:
            evicted, _ = self._cache.popitem(last=False)
            logger.info("LRU evict: model for %s removed from RAM cache", evicted)
        self._cache[symbol] = _CacheEntry(model=model)
        self._cache.move_to_end(symbol)

    def _next_version(self, symbol: str) -> int:
        models = self._metadata.get(symbol, [])
        return max((m.version for m in models), default=0) + 1

    def _get_best_metadata(self, symbol: str) -> Optional[ModelMetadata]:
        models = self._metadata.get(symbol, [])
        if not models:
            return None
        return max(models, key=lambda m: m.auc_roc)

    def _update_best(self, symbol: str) -> None:
        models = self._metadata.get(symbol, [])
        if not models:
            return
        best = max(models, key=lambda m: m.auc_roc)
        for m in models:
            m.is_best = (m.model_id == best.model_id)

    def _cleanup_old_models(self, symbol: str) -> None:
        models = self._metadata.get(symbol, [])
        if len(models) <= self.MAX_MODELS_PER_SYMBOL:
            return
        sorted_models = sorted(models, key=lambda m: m.trained_at)
        to_delete = sorted_models[: len(models) - self.MAX_MODELS_PER_SYMBOL]
        for m in to_delete:
            if not m.is_best and os.path.exists(m.file_path):
                os.remove(m.file_path)
                logger.debug("old model deleted: %s", m.file_path)
        self._metadata[symbol] = [
            m for m in models if m not in to_delete or m.is_best
        ]

    def _save_metadata(self) -> None:
        data = {
            symbol: [m.to_dict() for m in models]
            for symbol, models in self._metadata.items()
        }
        with open(self.METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_metadata(self) -> None:
        if not os.path.exists(self.METADATA_FILE):
            return
        try:
            with open(self.METADATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for symbol, models_data in data.items():
                self._metadata[symbol] = [ModelMetadata(**m) for m in models_data]
            logger.info("metadata loaded — %d symbols", len(self._metadata))
        except Exception as exc:
            logger.error("failed to load metadata: %s", exc)
