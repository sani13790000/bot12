"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: ML Engine — یادگیری ماشین برای پیش‌بینی کیفیت سیگنال

این ماژول مسئول:
  • آموزش مدل XGBoost با داده‌های معاملاتی تاریخی
  • پیش‌بینی احتمال موفقیت سیگنال‌های جدید
  • مدیریت چندین مدل به تفکیک نوع معامله (BUY/SELL/کلی)
  • ذخیره و بارگذاری مدل‌ها از فایل
"""
from __future__ import annotations

import os
import pickle
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..core.logger import get_logger

logger = get_logger("intelligence.ml_engine")


class ModelType(str, Enum):
    OVERALL = "overall"
    BUY     = "buy"
    SELL    = "sell"


@dataclass
class MLPrediction:
    success_probability: float
    model_type:          ModelType
    features_used:       int
    is_reliable:         bool
    confidence:          float
    metadata:            Dict[str, Any] = field(default_factory=dict)

    @property
    def should_trade(self) -> bool:
        return self.success_probability >= 0.55 and self.is_reliable


@dataclass
class TrainingResult:
    model_type:              ModelType
    auc_roc:                 float
    accuracy:                float
    precision:               float
    recall:                  float
    f1_score:                float
    feature_importance:      Dict[str, float]
    training_time_seconds:   float
    n_samples:               int
    is_reliable:             bool

    @property
    def summary(self) -> str:
        return (
            f"{self.model_type.value}: AUC={self.auc_roc:.3f} "
            f"Acc={self.accuracy:.3f} F1={self.f1_score:.3f} "
            f"n={self.n_samples}"
        )


class MLEngine:
    """
    موتور ML برای پیش‌بینی کیفیت سیگنال.

    از XGBoost برای آموزش سه مدل موازی استفاده می‌کند:
      - overall: همه معاملات
      - buy:     فقط خرید
      - sell:    فقط فروش

    اگر xgboost نصب نباشد, gracefully به fallback می‌رود.
    """

    MIN_SAMPLES = 30
    MIN_AUC     = 0.55

    def __init__(self, model_dir: str = "models/ml") -> None:
        self._model_dir      = Path(model_dir)
        self._models:        Dict[ModelType, Any]             = {}
        self._results:       Dict[ModelType, TrainingResult]  = {}
        self._feature_names: List[str]                        = []
        self._xgb_available = self._check_xgb()

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        if not self._models:
            return MLPrediction(
                success_probability=0.5,
                model_type=ModelType.OVERALL,
                features_used=0,
                is_reliable=False,
                confidence=0.0,
                metadata={"reason": "no_model_trained"},
            )
        direction  = str(features.get("direction", "")).upper()
        model_type = ModelType.OVERALL
        if direction == "BUY"  and ModelType.BUY  in self._models:
            model_type = ModelType.BUY
        elif direction == "SELL" and ModelType.SELL in self._models:
            model_type = ModelType.SELL
        model  = self._models[model_type]
        result = self._results.get(model_type)
        try:
            X    = self._build_feature_vector(features)
            prob = float(model.predict_proba(X)[0][1])
            conf = min(1.0, abs(prob - 0.5) * 2)
            return MLPrediction(
                success_probability=prob,
                model_type=model_type,
                features_used=X.shape[1],
                is_reliable=result.is_reliable if result else False,
                confidence=conf,
                metadata={"auc_roc": result.auc_roc if result else 0.0},
            )
        except Exception as exc:
            logger.warning(f"Prediction error: {exc}")
            return MLPrediction(
                success_probability=0.5,
                model_type=model_type,
                features_used=0,
                is_reliable=False,
                confidence=0.0,
                metadata={"error": str(exc)},
            )

    def train(self, memory) -> Dict[ModelType, TrainingResult]:
        if not self._xgb_available:
            logger.warning("XGBoost نصب نیست — آموزش ML ممکن نیست")
            return {}
        from .trade_memory import TradeOutcome
        all_trades = memory.get_all()
        if len(all_trades) < self.MIN_SAMPLES:
            logger.info(f"داده کافی برای آموزش نیست: {len(all_trades)} < {self.MIN_SAMPLES}")
            return {}
        results: Dict[ModelType, TrainingResult] = {}
        r = self._train_subset(all_trades, ModelType.OVERALL)
        if r:
            results[ModelType.OVERALL] = r
        buy_trades  = [t for t in all_trades if str(t.direction).upper() == "BUY"]
        if len(buy_trades) >= self.MIN_SAMPLES:
            r = self._train_subset(buy_trades, ModelType.BUY)
            if r:
                results[ModelType.BUY] = r
        sell_trades = [t for t in all_trades if str(t.direction).upper() == "SELL"]
        if len(sell_trades) >= self.MIN_SAMPLES:
            r = self._train_subset(sell_trades, ModelType.SELL)
            if r:
                results[ModelType.SELL] = r
        self._results.update(results)
        logger.info(f"آموزش ML کامل شد: {list(results.keys())}")
        return results

    def save_models(self) -> bool:
        try:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "models":        self._models,
                "results":       self._results,
                "feature_names": self._feature_names,
            }
            path = self._model_dir / "ml_models.pkl"
            with open(path, "wb") as f:
                pickle.dump(payload, f)
            logger.info(f"مدل‌های ML ذخیره شدند: {path}")
            return True
        except Exception as exc:
            logger.error(f"خطا در ذخیره مدل: {exc}")
            return False

    def load_models(self) -> bool:
        path = self._model_dir / "ml_models.pkl"
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)
            self._models        = payload.get("models", {})
            self._results       = payload.get("results", {})
            self._feature_names = payload.get("feature_names", [])
            logger.info(f"مدل‌های ML بارگذاری شدند: {list(self._models.keys())}")
            return True
        except Exception as exc:
            logger.warning(f"خطا در بارگذاری مدل: {exc}")
            return False

    def get_feature_importance(self, model_type: ModelType = ModelType.OVERALL) -> Dict[str, float]:
        result = self._results.get(model_type)
        return result.feature_importance if result else {}

    def is_trained(self) -> bool:
        return bool(self._models)

    def _train_subset(self, trades: list, model_type: ModelType) -> Optional[TrainingResult]:
        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import (roc_auc_score, accuracy_score,
                                         precision_score, recall_score, f1_score)
            from .trade_memory import TradeOutcome
            X_list, y_list = [], []
            for trade in trades:
                try:
                    feats = trade.to_ml_features()
                    label = 1 if trade.outcome == TradeOutcome.WIN else 0
                    X_list.append(list(feats.values()))
                    y_list.append(label)
                    if not self._feature_names:
                        self._feature_names = list(feats.keys())
                except Exception:
                    continue
            if len(X_list) < self.MIN_SAMPLES:
                return None
            X = np.array(X_list, dtype=np.float32)
            y = np.array(y_list, dtype=np.int32)
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            t0  = time.time()
            clf = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                use_label_encoder=False, eval_metric="logloss",
                random_state=42, verbosity=0,
            )
            clf.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
            elapsed      = time.time() - t0
            y_pred_prob  = clf.predict_proba(X_te)[:, 1]
            y_pred       = clf.predict(X_te)
            auc = float(roc_auc_score(y_te, y_pred_prob)) if len(set(y_te)) > 1 else 0.5
            acc = float(accuracy_score(y_te, y_pred))
            pre = float(precision_score(y_te, y_pred, zero_division=0))
            rec = float(recall_score(y_te, y_pred, zero_division=0))
            f1  = float(f1_score(y_te, y_pred, zero_division=0))
            feat_imp: Dict[str, float] = {}
            if self._feature_names and hasattr(clf, "feature_importances_"):
                for name, imp in zip(self._feature_names, clf.feature_importances_):
                    feat_imp[name] = float(imp)
            result = TrainingResult(
                model_type=model_type, auc_roc=auc, accuracy=acc,
                precision=pre, recall=rec, f1_score=f1,
                feature_importance=feat_imp,
                training_time_seconds=elapsed,
                n_samples=len(X_list),
                is_reliable=auc >= self.MIN_AUC,
            )
            self._models[model_type] = clf
            logger.info(f"مدل {model_type.value} آموزش دید: {result.summary}")
            return result
        except Exception as exc:
            logger.error(f"خطا در آموزش مدل {model_type.value}: {exc}")
            return None

    def _build_feature_vector(self, features: Dict[str, float]) -> np.ndarray:
        if self._feature_names:
            vec = [float(features.get(name, 0.0)) for name in self._feature_names]
        else:
            vec = [float(v) for v in features.values()]
        return np.array([vec], dtype=np.float32)

    @staticmethod
    def _check_xgb() -> bool:
        try:
            import xgboost  # noqa: F401
            return True
        except ImportError:
            return False
