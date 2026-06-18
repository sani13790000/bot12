"""Model Manager — Phase 5: Version registry, LRU cache, staleness, drift-triggered reload."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CACHED_MODELS = 3
STALENESS_HOURS = 24


@dataclass
class ModelVersion:
    version: str
    symbol: str
    model_type: str
    accuracy: float
    f1_score: float
    n_samples: int
    trained_at: datetime
    file_path: str
    oos_accuracy: float = 0.0
    overfit_ratio: float = 1.0
    drift_score: float = 0.0
    is_active: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "symbol": self.symbol,
            "model_type": self.model_type,
            "accuracy": self.accuracy,
            "f1_score": self.f1_score,
            "n_samples": self.n_samples,
            "trained_at": self.trained_at.isoformat(),
            "file_path": self.file_path,
            "oos_accuracy": self.oos_accuracy,
            "overfit_ratio": self.overfit_ratio,
            "drift_score": self.drift_score,
            "is_active": self.is_active,
        }


@dataclass
class _CacheEntry:
    model: Any
    loaded_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)
    access_count: int = 0
    version: str = "1.0"

    def touch(self) -> None:
        self.last_accessed = time.monotonic()
        self.access_count += 1

    @property
    def age_hours(self) -> float:
        return (time.monotonic() - self.loaded_at) / 3600.0

    @property
    def is_stale(self) -> bool:
        return self.age_hours > STALENESS_HOURS


class ModelManager:
    """Singleton model manager with LRU cache, version registry, and drift-triggered reload."""

    _instance: Optional["ModelManager"] = None

    def __new__(cls, model_dir: Optional[Path] = None) -> "ModelManager":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False
            cls._instance = inst
        return cls._instance

    def __init__(self, model_dir: Optional[Path] = None) -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._model_dir = model_dir or Path("models")
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._registry: Dict[str, List[ModelVersion]] = {}  # symbol → versions
        self._initialized = True
        self._load_registry()
        logger.info("[ModelManager] initialized, model_dir=%s", self._model_dir)

    # ------------------------------------------------------------------ #
    #  PUBLIC API
    # ------------------------------------------------------------------ #

    def save_model(self, symbol: str, model: Any, training_result: Any) -> str:
        """Persist model + register new version. Returns version string."""
        import pickle

        # Determine next version
        existing = self._registry.get(symbol, [])
        if existing:
            last_v = existing[-1].version
            try:
                major, minor = last_v.split(".")
                new_v = f"{major}.{int(minor) + 1}"
            except Exception:
                new_v = f"1.{len(existing)}"
        else:
            new_v = "1.0"

        file_name = f"{symbol}_v{new_v.replace('.', '_')}.pkl"
        file_path = self._model_dir / file_name
        file_path.write_bytes(pickle.dumps(model))

        mv = ModelVersion(
            version=new_v,
            symbol=symbol,
            model_type=getattr(training_result, "model_type", "direction"),
            accuracy=getattr(training_result, "accuracy", 0.0),
            f1_score=getattr(training_result, "f1_score", 0.0),
            n_samples=getattr(training_result, "n_samples", 0),
            trained_at=datetime.utcnow(),
            file_path=str(file_path),
            oos_accuracy=getattr(training_result, "avg_oos_accuracy", 0.0),
            overfit_ratio=getattr(training_result, "avg_overfit_ratio", 1.0),
            drift_score=getattr(training_result, "drift_score", 0.0),
        )

        if symbol not in self._registry:
            self._registry[symbol] = []
        # Deactivate previous versions
        for v in self._registry[symbol]:
            v.is_active = False
        self._registry[symbol].append(mv)
        self._save_registry()

        # Invalidate cache for this symbol
        if symbol in self._cache:
            del self._cache[symbol]
            logger.info("[ModelManager] cache invalidated for %s after save", symbol)

        logger.info("[ModelManager] saved %s v%s acc=%.3f oos=%.3f", symbol, new_v, mv.accuracy, mv.oos_accuracy)
        return new_v

    def load_model(self, symbol: str, force_reload: bool = False) -> Optional[Any]:
        """Load model from LRU cache or disk. Auto-evicts stale entries."""
        # Cache hit
        if symbol in self._cache and not force_reload:
            entry = self._cache[symbol]
            if not entry.is_stale:
                self._cache.move_to_end(symbol)  # LRU update
                entry.touch()
                return entry.model
            else:
                logger.info("[ModelManager] %s cache stale (%.1fh) — reloading", symbol, entry.age_hours)
                del self._cache[symbol]

        # Load from disk
        model = self._load_from_disk(symbol)
        if model is None:
            return None

        version = self._get_active_version(symbol)
        self._add_to_cache(symbol, model, version)
        return model

    def get_active_version(self, symbol: str) -> Optional[ModelVersion]:
        versions = self._registry.get(symbol, [])
        active = [v for v in versions if v.is_active]
        return active[-1] if active else (versions[-1] if versions else None)

    def list_models(self) -> List[Dict[str, Any]]:
        result = []
        for symbol, versions in self._registry.items():
            active = self.get_active_version(symbol)
            if active:
                result.append(active.to_dict())
        return result

    def get_staleness_info(self, symbol: str) -> Dict[str, Any]:
        if symbol not in self._cache:
            return {"cached": False, "symbol": symbol}
        entry = self._cache[symbol]
        return {
            "cached": True,
            "symbol": symbol,
            "age_hours": round(entry.age_hours, 2),
            "is_stale": entry.is_stale,
            "access_count": entry.access_count,
            "version": entry.version,
        }

    def invalidate(self, symbol: str) -> None:
        if symbol in self._cache:
            del self._cache[symbol]
            logger.info("[ModelManager] cache invalidated: %s", symbol)

    def get_registry_summary(self) -> Dict[str, Any]:
        return {
            "total_symbols": len(self._registry),
            "cached_symbols": len(self._cache),
            "models": [
                {
                    "symbol": s,
                    "versions": len(vs),
                    "active_version": vs[-1].version if vs else None,
                    "active_accuracy": vs[-1].accuracy if vs else 0.0,
                    "active_oos": vs[-1].oos_accuracy if vs else 0.0,
                }
                for s, vs in self._registry.items()
            ],
        }

    def should_retrain(self, symbol: str, drift_score: float = 0.0) -> bool:
        """True if no model, stale in cache, or drift triggered."""
        if symbol not in self._registry:
            return True
        if drift_score > 0.5:
            logger.warning("[ModelManager] drift=%.3f for %s — retrain recommended", drift_score, symbol)
            return True
        active = self.get_active_version(symbol)
        if active is None:
            return True
        age = datetime.utcnow() - active.trained_at
        if age > timedelta(hours=STALENESS_HOURS):
            return True
        return False

    # ------------------------------------------------------------------ #
    #  INTERNAL
    # ------------------------------------------------------------------ #

    def _add_to_cache(self, symbol: str, model: Any, version: str) -> None:
        # LRU eviction
        while len(self._cache) >= MAX_CACHED_MODELS:
            evicted, _ = self._cache.popitem(last=False)
            logger.info("[ModelManager] LRU evict: %s", evicted)
        self._cache[symbol] = _CacheEntry(model=model, version=version)
        self._cache.move_to_end(symbol)

    def _load_from_disk(self, symbol: str) -> Optional[Any]:
        active = self.get_active_version(symbol)
        if active is None:
            logger.warning("[ModelManager] no registry entry for %s", symbol)
            return None
        path = Path(active.file_path)
        if not path.exists():
            logger.warning("[ModelManager] file not found: %s", path)
            return None
        try:
            import pickle
            model = pickle.loads(path.read_bytes())
            logger.info("[ModelManager] loaded %s v%s from disk", symbol, active.version)
            return model
        except Exception as exc:
            logger.error("[ModelManager] load error %s: %s", symbol, exc)
            return None

    def _get_active_version(self, symbol: str) -> str:
        active = self.get_active_version(symbol)
        return active.version if active else "1.0"

    def _save_registry(self) -> None:
        try:
            import json
            reg_path = self._model_dir / "model_registry.json"
            data: Dict[str, Any] = {}
            for symbol, versions in self._registry.items():
                data[symbol] = [v.to_dict() for v in versions]
            reg_path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as exc:
            logger.error("[ModelManager] save registry error: %s", exc)

    def _load_registry(self) -> None:
        try:
            import json
            reg_path = self._model_dir / "model_registry.json"
            if not reg_path.exists():
                return
            data = json.loads(reg_path.read_text())
            for symbol, versions in data.items():
                self._registry[symbol] = [
                    ModelVersion(
                        version=v["version"],
                        symbol=v["symbol"],
                        model_type=v["model_type"],
                        accuracy=v["accuracy"],
                        f1_score=v["f1_score"],
                        n_samples=v["n_samples"],
                        trained_at=datetime.fromisoformat(v["trained_at"]),
                        file_path=v["file_path"],
                        oos_accuracy=v.get("oos_accuracy", 0.0),
                        overfit_ratio=v.get("overfit_ratio", 1.0),
                        drift_score=v.get("drift_score", 0.0),
                        is_active=v.get("is_active", True),
                    )
                    for v in versions
                ]
            logger.info("[ModelManager] registry loaded: %d symbols", len(self._registry))
        except Exception as exc:
            logger.warning("[ModelManager] load registry error: %s", exc)
