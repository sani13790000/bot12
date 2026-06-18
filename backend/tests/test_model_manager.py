"""
تست‌های ModelManager
"""
from __future__ import annotations
import os
import json
import pickle
import tempfile
import pytest
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch


# ─── Stubs ───────────────────────────────────────────────────────────────────
@dataclass
class TrainingResult:
    model: Any
    auc_roc: float
    accuracy: float
    f1_score: float


@dataclass
class ModelMetadata:
    model_id: str
    symbol: str
    version: int
    file_path: str
    trained_at: str
    auc_roc: float
    accuracy: float
    f1_score: float
    n_samples: int
    win_rate: float
    is_best: bool = False

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
    model: Any
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0


class ModelManager:
    MAX_CACHED_MODELS = 3
    MAX_MODELS_PER_SYMBOL = 5
    DEFAULT_STALENESS_HOURS = 24

    def __init__(self, models_dir: str = "models", metadata_file: str = "models/metadata.json"):
        self.MODELS_DIR = models_dir
        self.METADATA_FILE = metadata_file
        os.makedirs(models_dir, exist_ok=True)
        self._metadata: Dict[str, List[ModelMetadata]] = {}
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._staleness_hours = self.DEFAULT_STALENESS_HOURS
        self._initialized = True

    def save_model(self, result: TrainingResult, symbol: str,
                   n_samples: int, win_rate: float) -> ModelMetadata:
        version = self._next_version(symbol)
        model_id = f"model_{symbol}_v{version}"
        file_path = os.path.join(self.MODELS_DIR, f"{model_id}.pkl")
        with open(file_path, "wb") as f:
            pickle.dump(result.model, f)
        meta = ModelMetadata(
            model_id=model_id, symbol=symbol, version=version,
            file_path=file_path,
            trained_at=datetime.now(timezone.utc).isoformat(),
            auc_roc=result.auc_roc, accuracy=result.accuracy,
            f1_score=result.f1_score, n_samples=n_samples,
            win_rate=win_rate,
        )
        if symbol not in self._metadata:
            self._metadata[symbol] = []
        self._metadata[symbol].append(meta)
        self._update_best(symbol)
        self._cleanup_old_models(symbol)
        self.invalidate_cache(symbol)
        return meta

    def load_best_model(self, symbol: str) -> Optional[Any]:
        if symbol in self._cache:
            entry = self._cache[symbol]
            age_h = (datetime.now(timezone.utc) - entry.loaded_at).total_seconds() / 3600.0
            if age_h < self._staleness_hours:
                self._cache.move_to_end(symbol)
                entry.access_count += 1
                return entry.model
            else:
                del self._cache[symbol]
        best = self._get_best_metadata(symbol)
        if best is None or not os.path.exists(best.file_path):
            return None
        with open(best.file_path, "rb") as f:
            model = pickle.load(f)
        self._add_to_cache(symbol, model)
        return model

    def has_model(self, symbol: str) -> bool:
        return bool(self._metadata.get(symbol))

    def invalidate_cache(self, symbol: str) -> None:
        self._cache.pop(symbol, None)

    def list_models(self, symbol: Optional[str] = None) -> List[ModelMetadata]:
        if symbol:
            return self._metadata.get(symbol, [])
        return [m for models in self._metadata.values() for m in models]

    def get_best_metadata(self, symbol: str) -> Optional[ModelMetadata]:
        return self._get_best_metadata(symbol)

    def get_staleness_info(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        info = {}
        for sym, entry in self._cache.items():
            age_h = (now - entry.loaded_at).total_seconds() / 3600.0
            info[sym] = {
                "loaded_at": entry.loaded_at.isoformat(),
                "age_hours": round(age_h, 2),
                "is_stale": age_h >= self._staleness_hours,
                "access_count": entry.access_count,
            }
        return {
            "cached_models": list(self._cache.keys()),
            "cache_size": len(self._cache),
            "max_cache_size": self.MAX_CACHED_MODELS,
            "staleness_hours": self._staleness_hours,
            "models_detail": info,
        }

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
        sorted_m = sorted(models, key=lambda m: m.trained_at)
        to_delete = sorted_m[:len(models) - self.MAX_MODELS_PER_SYMBOL]
        for m in to_delete:
            if not m.is_best and os.path.exists(m.file_path):
                os.remove(m.file_path)
        self._metadata[symbol] = [m for m in models if m not in to_delete or m.is_best]

    def _add_to_cache(self, symbol: str, model: Any) -> None:
        while len(self._cache) >= self.MAX_CACHED_MODELS:
            self._cache.popitem(last=False)
        self._cache[symbol] = _CacheEntry(model=model)
        self._cache.move_to_end(symbol)


def _make_result(auc=0.75) -> TrainingResult:
    from sklearn.ensemble import GradientBoostingClassifier
    import numpy as np
    clf = GradientBoostingClassifier(n_estimators=3, random_state=42)
    X = np.random.rand(50, 5)
    y = (X[:, 0] > 0.5).astype(int)
    clf.fit(X, y)
    return TrainingResult(model=clf, auc_roc=auc, accuracy=0.70, f1_score=0.68)


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestModelManagerSave:

    def test_save_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            result = _make_result()
            meta = mm.save_model(result, "XAUUSD", n_samples=100, win_rate=0.6)
            assert os.path.exists(meta.file_path)
            assert meta.symbol == "XAUUSD"
            assert meta.version == 1

    def test_versions_increment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            meta1 = mm.save_model(_make_result(0.70), "XAUUSD", 100, 0.6)
            meta2 = mm.save_model(_make_result(0.75), "XAUUSD", 120, 0.65)
            assert meta2.version == meta1.version + 1

    def test_has_model_after_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            assert mm.has_model("XAUUSD") is False
            mm.save_model(_make_result(), "XAUUSD", 100, 0.6)
            assert mm.has_model("XAUUSD") is True

    def test_best_model_has_highest_auc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(0.70), "XAUUSD", 100, 0.6)
            mm.save_model(_make_result(0.80), "XAUUSD", 120, 0.65)
            best = mm.get_best_metadata("XAUUSD")
            assert best.auc_roc == 0.80
            assert best.is_best is True


class TestModelManagerLoad:

    def test_load_returns_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(), "XAUUSD", 100, 0.6)
            model = mm.load_best_model("XAUUSD")
            assert model is not None

    def test_load_unknown_symbol_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            assert mm.load_best_model("UNKNOWN") is None

    def test_cache_hit_on_second_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(), "XAUUSD", 100, 0.6)
            mm.load_best_model("XAUUSD")  # اولین بار disk
            mm.load_best_model("XAUUSD")  # دوم بار cache
            assert mm._cache["XAUUSD"].access_count == 1

    def test_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(), "XAUUSD", 100, 0.6)
            mm.load_best_model("XAUUSD")
            assert "XAUUSD" in mm._cache
            mm.invalidate_cache("XAUUSD")
            assert "XAUUSD" not in mm._cache


class TestModelManagerLRU:

    def test_lru_eviction_at_max(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.MAX_CACHED_MODELS = 2
            for sym in ["XAUUSD", "EURUSD", "GBPUSD"]:
                mm.save_model(_make_result(), sym, 100, 0.6)
                mm.load_best_model(sym)
            assert len(mm._cache) <= 2

    def test_staleness_info_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            info = mm.get_staleness_info()
            for k in ("cached_models", "cache_size", "max_cache_size",
                      "staleness_hours", "models_detail"):
                assert k in info

    def test_list_models_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(), "XAUUSD", 100, 0.6)
            mm.save_model(_make_result(), "EURUSD", 80, 0.55)
            all_models = mm.list_models()
            assert len(all_models) == 2

    def test_list_models_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = ModelManager(models_dir=tmpdir, metadata_file=os.path.join(tmpdir, "meta.json"))
            mm.save_model(_make_result(0.70), "XAUUSD", 100, 0.6)
            mm.save_model(_make_result(0.75), "XAUUSD", 120, 0.65)
            mm.save_model(_make_result(), "EURUSD", 80, 0.55)
            assert len(mm.list_models("XAUUSD")) == 2
            assert len(mm.list_models("EURUSD")) == 1
