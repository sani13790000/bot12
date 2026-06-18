"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: ModelManager

وظیفه:
  مدیریت کامل چرخه عمر مدل‌های XGBoost:
  • ذخیره و بارگذاری مدل‌ها
  • versioning (هر آموزش یک version جدید)
  • نگه‌داری بهترین مدل (best model)
  • پاکسازی مدل‌های قدیمی
  • متادیتا برای هر مدل

ساختار پوشه:
  models/
    galaxy_vast_XAUUSD_v1_20240115_143022.pkl
    galaxy_vast_XAUUSD_v2_20240120_091500.pkl
    galaxy_vast_best_XAUUSD.pkl   ← لینک به بهترین مدل
    metadata.json                 ← اطلاعات همه مدل‌ها
"""

from __future__ import annotations

import json
import os
import pickle
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger
from .xgboost_trainer import TrainingResult

logger = get_logger("ai_prediction.model_manager")


@dataclass
class ModelMetadata:
    """
    متادیتای یک مدل ذخیره‌شده.
    """
    model_id:       str
    symbol:         str
    version:        int
    file_path:      str
    trained_at:     str          # ISO format
    auc_roc:        float
    accuracy:       float
    f1_score:       float
    n_samples:      int
    win_rate:       float
    is_best:        bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


class ModelManager:
    """
    مدیریت‌کننده مدل‌های XGBoost.

    یک instance برای کل سیستم — singleton pattern.
    """

    _instance: Optional["ModelManager"] = None

    MODELS_DIR:    str = "models"
    METADATA_FILE: str = "models/metadata.json"
    MAX_MODELS_PER_SYMBOL: int = 5   # نگه‌داشتن حداکثر ۵ مدل per symbol

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
        self._loaded_models: Dict[str, Any] = {}   # symbol → model object
        self._load_metadata()
        self._initialized = True
        logger.info("ModelManager initialized — models_dir=%s", self.MODELS_DIR)

    # ─── public API ───────────────────────────────────────────────────────────

    def save_model(
        self,
        result:   TrainingResult,
        symbol:   str,
        n_samples: int,
        win_rate:  float,
    ) -> ModelMetadata:
        """
        ذخیره مدل جدید و ثبت متادیتا.

        Args:
            result:    نتیجه آموزش
            symbol:    نماد معاملاتی (مثل XAUUSD)
            n_samples: تعداد نمونه‌های آموزشی
            win_rate:  نرخ موفقیت در dataset

        Returns:
            ModelMetadata: اطلاعات مدل ذخیره‌شده
        """
        version   = self._next_version(symbol)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        model_id  = f"galaxy_vast_{symbol}_v{version}_{timestamp}"
        file_path = os.path.join(self.MODELS_DIR, f"{model_id}.pkl")

        # ذخیره مدل
        with open(file_path, "wb") as f:
            pickle.dump(result.model, f, protocol=pickle.HIGHEST_PROTOCOL)

        metadata = ModelMetadata(
            model_id   = model_id,
            symbol     = symbol,
            version    = version,
            file_path  = file_path,
            trained_at = datetime.utcnow().isoformat(),
            auc_roc    = result.auc_roc,
            accuracy   = result.accuracy,
            f1_score   = result.f1_score,
            n_samples  = n_samples,
            win_rate   = win_rate,
        )

        # ثبت در metadata
        if symbol not in self._metadata:
            self._metadata[symbol] = []
        self._metadata[symbol].append(metadata)

        # به‌روزرسانی best model
        self._update_best(symbol)

        # پاکسازی مدل‌های قدیمی
        self._cleanup_old_models(symbol)

        self._save_metadata()
        logger.info("model saved — %s (AUC=%.3f)", model_id, result.auc_roc)
        return metadata

    def load_best_model(self, symbol: str) -> Optional[Any]:
        """
        بارگذاری بهترین مدل برای یک نماد.

        Returns:
            مدل XGBoost یا None اگر مدلی وجود نداشته باشد
        """
        if symbol in self._loaded_models:
            return self._loaded_models[symbol]

        best = self._get_best_metadata(symbol)
        if best is None:
            logger.warning("no model found for symbol %s", symbol)
            return None

        if not os.path.exists(best.file_path):
            logger.error("model file not found: %s", best.file_path)
            return None

        with open(best.file_path, "rb") as f:
            model = pickle.load(f)

        self._loaded_models[symbol] = model
        logger.info("best model loaded for %s — v%d (AUC=%.3f)", symbol, best.version, best.auc_roc)
        return model

    def get_best_metadata(self, symbol: str) -> Optional[ModelMetadata]:
        """متادیتای بهترین مدل برای یک نماد."""
        return self._get_best_metadata(symbol)

    def list_models(self, symbol: Optional[str] = None) -> List[ModelMetadata]:
        """لیست همه مدل‌ها (یا برای یک نماد خاص)."""
        if symbol:
            return self._metadata.get(symbol, [])
        return [m for models in self._metadata.values() for m in models]

    def invalidate_cache(self, symbol: str) -> None:
        """پاک کردن مدل cache‌شده (بعد از آموزش جدید)."""
        self._loaded_models.pop(symbol, None)
        logger.debug("model cache invalidated for %s", symbol)

    def has_model(self, symbol: str) -> bool:
        """آیا مدل آموزش‌دیده‌ای برای این نماد وجود دارد؟"""
        return bool(self._metadata.get(symbol))

    # ─── private ──────────────────────────────────────────────────────────────

    def _next_version(self, symbol: str) -> int:
        models = self._metadata.get(symbol, [])
        return max((m.version for m in models), default=0) + 1

    def _get_best_metadata(self, symbol: str) -> Optional[ModelMetadata]:
        models = self._metadata.get(symbol, [])
        if not models:
            return None
        return max(models, key=lambda m: m.auc_roc)

    def _update_best(self, symbol: str) -> None:
        """علامت‌گذاری بهترین مدل."""
        models = self._metadata.get(symbol, [])
        if not models:
            return
        best = max(models, key=lambda m: m.auc_roc)
        for m in models:
            m.is_best = (m.model_id == best.model_id)

    def _cleanup_old_models(self, symbol: str) -> None:
        """حذف مدل‌های قدیمی‌تر از حد مجاز."""
        models = self._metadata.get(symbol, [])
        if len(models) <= self.MAX_MODELS_PER_SYMBOL:
            return

        # مرتب‌سازی از قدیم به جدید — حذف قدیمی‌ترها
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
