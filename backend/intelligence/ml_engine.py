"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: MLEngine — یادگیری ماشین

مدل‌ها:
  • XGBoost   ← gradient boosting سریع و دقیق
  • LightGBM  ← مناسب داده‌های بزرگ
  • CatBoost  ← مقاوم در برابر overfitting

وظیفه:
  یادگیری از تاریخچه معاملات برای پیش‌بینی موفقیت سیگنال‌های جدید.
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .trade_memory import TradeMemory, TradeContext, TradeOutcome
from ..core.logger import get_logger

logger = get_logger("intelligence.ml_engine")


class ModelType(str, Enum):
    XGBOOST  = "xgboost"
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    ENSEMBLE = "ensemble"


@dataclass
class MLPrediction:
    """نتیجه پیش‌بینی ML"""
    win_probability: float
    confidence: float
    is_reliable: bool
    recommendation: str          # STRONG_BUY / BUY / WAIT / SELL / STRONG_SELL
    model_type: ModelType
    feature_importances: Dict[str, float]
    training_samples: int

    # فیلدهای اضافی
    model_agreement: float = 0.0  # توافق بین مدل‌ها
    xgb_prob:  Optional[float] = None
    lgb_prob:  Optional[float] = None
    cat_prob:  Optional[float] = None

    @property
    def adjusted_score(self) -> float:
        """
        امتیاز تنظیم‌شده بر اساس احتمال برد و اطمینان.
        مقدار: 0.0 (بد) تا 100.0 (عالی)
        """
        base = self.win_probability * 100
        conf_factor = 0.7 + (self.confidence * 0.3)
        return min(100.0, base * conf_factor)


@dataclass
class TrainingResult:
    """نتیجه آموزش مدل"""
    model_type: ModelType
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    auc_roc: float = 0.0
    training_samples: int = 0
    validation_samples: int = 0
    feature_importances: Dict[str, float] = field(default_factory=dict)
    is_reliable: bool = False


class MLEngine:
    """
    موتور یادگیری ماشین Galaxy Vast.

    وظیفه:
      آموزش مدل‌های ML بر روی تاریخچه معاملات و
      پیش‌بینی احتمال موفقیت سیگنال‌های جدید.
    """

    MIN_TRAINING_SAMPLES = 50
    RELIABLE_THRESHOLD   = 100
    CONFIDENCE_THRESHOLD = 0.55

    def __init__(self, model_dir: str = "models/ml") -> None:
        self._model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        # مدل‌های آموزش‌دیده
        self._models: Dict[ModelType, Any] = {}
        self._training_results: Dict[ModelType, TrainingResult] = {}
        self._feature_names: List[str] = []
        self._is_trained = False

    def train(self, memory: TradeMemory) -> Dict[ModelType, TrainingResult]:
        """
        آموزش همه مدل‌ها بر روی داده‌های موجود در حافظه.

        Args:
            memory: حافظه معاملاتی حاوی تاریخچه trades

        Returns:
            دیکشنری از نتایج آموزش برای هر مدل
        """
        trades = memory.get_all_trades()
        if len(trades) < self.MIN_TRAINING_SAMPLES:
            logger.warning(
                f"نمونه آموزش کافی نیست: {len(trades)} < {self.MIN_TRAINING_SAMPLES}"
            )
            return {}

        # استخراج features و labels
        X, y, feature_names = self._prepare_data(trades)
        self._feature_names = feature_names

        results: Dict[ModelType, TrainingResult] = {}

        # آموزش XGBoost
        xgb_result = self._train_xgboost(X, y, feature_names)
        if xgb_result.auc_roc > 0:
            results[ModelType.XGBOOST] = xgb_result
            self._training_results[ModelType.XGBOOST] = xgb_result

        # آموزش LightGBM
        lgb_result = self._train_lightgbm(X, y, feature_names)
        if lgb_result.auc_roc > 0:
            results[ModelType.LIGHTGBM] = lgb_result
            self._training_results[ModelType.LIGHTGBM] = lgb_result

        # آموزش CatBoost
        cat_result = self._train_catboost(X, y, feature_names)
        if cat_result.auc_roc > 0:
            results[ModelType.CATBOOST] = cat_result
            self._training_results[ModelType.CATBOOST] = cat_result

        self._is_trained = len(self._models) > 0

        if self._is_trained:
            self.save_models()
            logger.info(
                f"آموزش کامل شد: {len(self._models)} مدل، "
                f"{len(trades)} معامله"
            )

        return results

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        """
        پیش‌بینی احتمال موفقیت سیگنال.

        Args:
            features: بردار ویژگی‌های سیگنال

        Returns:
            MLPrediction حاوی احتمال برد و توصیه
        """
        if not self._is_trained or not self._models:
            # بارگذاری مدل‌ها اگر موجود باشند
            if not self.load_models():
                return MLPrediction(
                    win_probability=0.5,
                    confidence=0.0,
                    is_reliable=False,
                    recommendation="WAIT",
                    model_type=ModelType.XGBOOST,
                    feature_importances={},
                    training_samples=0,
                )

        # آماده‌سازی بردار features
        feature_vector = np.array(
            [features.get(f, 0.0) for f in self._feature_names]
        ).reshape(1, -1)

        predictions: Dict[ModelType, float] = {}
        for model_type, model in self._models.items():
            try:
                prob = model.predict_proba(feature_vector)[0][1]
                predictions[model_type] = float(prob)
            except Exception as e:
                logger.error(f"خطا در پیش‌بینی {model_type}: {e}")

        if not predictions:
            return MLPrediction(
                win_probability=0.5,
                confidence=0.0,
                is_reliable=False,
                recommendation="WAIT",
                model_type=ModelType.XGBOOST,
                feature_importances={},
                training_samples=0,
            )

        # میانگین وزن‌دار بر اساس AUC هر مدل
        weighted_sum = 0.0
        weight_total = 0.0
        for model_type, prob in predictions.items():
            auc = self._training_results.get(model_type, TrainingResult(model_type)).auc_roc
            weight = max(0.5, auc)  # حداقل وزن 0.5
            weighted_sum += prob * weight
            weight_total += weight

        win_prob = weighted_sum / weight_total if weight_total > 0 else 0.5

        # محاسبه confidence بر اساس توافق مدل‌ها
        probs = list(predictions.values())
        if len(probs) > 1:
            std = float(np.std(probs))
            confidence = max(0.0, 1.0 - std * 4)  # std بالا → confidence پایین
        else:
            confidence = 0.6

        # انتخاب بهترین مدل بر اساس AUC
        best_model_type = max(
            predictions.keys(),
            key=lambda m: self._training_results.get(m, TrainingResult(m)).auc_roc
        )

        best_result = self._training_results.get(best_model_type, TrainingResult(best_model_type))
        is_reliable = best_result.is_reliable and confidence >= self.CONFIDENCE_THRESHOLD

        return MLPrediction(
            win_probability=round(win_prob, 4),
            confidence=round(confidence, 4),
            is_reliable=is_reliable,
            recommendation=self._get_recommendation(win_prob, is_reliable),
            model_type=best_model_type,
            feature_importances=best_result.feature_importances,
            training_samples=best_result.training_samples,
            model_agreement=round(1.0 - float(np.std(probs)) if len(probs) > 1 else 1.0, 4),
            xgb_prob=predictions.get(ModelType.XGBOOST),
            lgb_prob=predictions.get(ModelType.LIGHTGBM),
            cat_prob=predictions.get(ModelType.CATBOOST),
        )

    def save_models(self) -> None:
        """ذخیره مدل‌ها روی دیسک."""
        for model_type, model in self._models.items():
            path = os.path.join(self._model_dir, f"{model_type.value}_model.pkl")
            with open(path, "wb") as f:
                pickle.dump(model, f)

        # ذخیره metadata
        meta = {
            "feature_names": self._feature_names,
            "training_results": {
                mt.value: {
                    "accuracy": tr.accuracy,
                    "auc_roc": tr.auc_roc,
                    "training_samples": tr.training_samples,
                    "is_reliable": tr.is_reliable,
                }
                for mt, tr in self._training_results.items()
            }
        }
        meta_path = os.path.join(self._model_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"مدل‌ها ذخیره شدند: {self._model_dir}")

    def load_models(self) -> bool:
        """بارگذاری مدل‌ها از دیسک."""
        meta_path = os.path.join(self._model_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return False

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            self._feature_names = meta.get("feature_names", [])

            for model_type in ModelType:
                if model_type == ModelType.ENSEMBLE:
                    continue
                path = os.path.join(self._model_dir, f"{model_type.value}_model.pkl")
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        self._models[model_type] = pickle.load(f)

                    # بازسازی training result
                    tr_data = meta.get("training_results", {}).get(model_type.value, {})
                    tr = TrainingResult(model_type)
                    tr.accuracy = tr_data.get("accuracy", 0.0)
                    tr.auc_roc  = tr_data.get("auc_roc", 0.0)
                    tr.training_samples = tr_data.get("training_samples", 0)
                    tr.is_reliable = tr_data.get("is_reliable", False)
                    self._training_results[model_type] = tr

            self._is_trained = len(self._models) > 0
            if self._is_trained:
                logger.info(f"مدل‌ها بارگذاری شدند: {list(self._models.keys())}")
            return self._is_trained

        except Exception as e:
            logger.error(f"خطا در بارگذاری مدل‌ها: {e}")
            return False

    def _prepare_data(
        self,
        trades: List[TradeContext],
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """تبدیل تاریخچه معاملات به matrix features."""
        feature_dicts = [t.to_ml_features() for t in trades]
        if not feature_dicts:
            return np.array([]), np.array([]), []

        feature_names = sorted(feature_dicts[0].keys())
        X = np.array([[fd.get(f, 0.0) for f in feature_names] for fd in feature_dicts])
        y = np.array([1 if t.outcome == TradeOutcome.WIN else 0 for t in trades])
        return X, y, feature_names

    def _train_xgboost(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
    ) -> TrainingResult:
        """آموزش XGBoost."""
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=42,
            )
            result = self._calculate_metrics(model, X, y, feature_names, ModelType.XGBOOST)
            self._models[ModelType.XGBOOST] = model
            return result
        except ImportError:
            logger.warning("xgboost نصب نیست — از این مدل صرف‌نظر می‌شود")
            return TrainingResult(ModelType.XGBOOST)
        except Exception as e:
            logger.error(f"خطا در آموزش XGBoost: {e}")
            return TrainingResult(ModelType.XGBOOST)

    def _train_lightgbm(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
    ) -> TrainingResult:
        """آموزش LightGBM."""
        try:
            import lightgbm as lgb
            model = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbose=-1,
            )
            result = self._calculate_metrics(
                model, X, y, feature_names, ModelType.LIGHTGBM,
                fit_params={"callbacks": [lgb.early_stopping(20, verbose=False)]}
            )
            self._models[ModelType.LIGHTGBM] = model
            return result
        except ImportError:
            logger.warning("lightgbm نصب نیست")
            return TrainingResult(ModelType.LIGHTGBM)
        except Exception as e:
            logger.error(f"خطا در آموزش LightGBM: {e}")
            return TrainingResult(ModelType.LIGHTGBM)

    def _train_catboost(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
    ) -> TrainingResult:
        """آموزش CatBoost."""
        try:
            from catboost import CatBoostClassifier
            model = CatBoostClassifier(
                iterations=200,
                depth=6,
                learning_rate=0.05,
                random_seed=42,
                verbose=0,
            )
            result = self._calculate_metrics(model, X, y, feature_names, ModelType.CATBOOST)
            self._models[ModelType.CATBOOST] = model
            return result
        except ImportError:
            logger.warning("catboost نصب نیست")
            return TrainingResult(ModelType.CATBOOST)
        except Exception as e:
            logger.error(f"خطا در آموزش CatBoost: {e}")
            return TrainingResult(ModelType.CATBOOST)

    def _calculate_metrics(
        self,
        model: Any,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        model_type: ModelType,
        fit_params: Optional[Dict] = None,
    ) -> TrainingResult:
        """محاسبه متریک‌های آموزش با cross-validation."""
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score,
            f1_score, roc_auc_score
        )

        result = TrainingResult(model_type)
        n = len(X)
        result.training_samples = int(n * 0.8)
        result.validation_samples = n - result.training_samples

        try:
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            if fit_params:
                model.fit(X_train, y_train, **fit_params)
            else:
                model.fit(X_train, y_train)

            y_pred  = model.predict(X_val)
            y_proba = model.predict_proba(X_val)[:, 1]

            result.accuracy   = float(accuracy_score(y_val, y_pred))
            result.precision  = float(precision_score(y_val, y_pred, zero_division=0))
            result.recall     = float(recall_score(y_val, y_pred, zero_division=0))
            result.f1_score   = float(f1_score(y_val, y_pred, zero_division=0))
            result.auc_roc    = float(roc_auc_score(y_val, y_proba))
            result.is_reliable = (
                result.training_samples >= self.RELIABLE_THRESHOLD
                and result.auc_roc >= 0.55
            )

            # Feature importances
            if hasattr(model, "feature_importances_"):
                imps = model.feature_importances_
                total = imps.sum()
                result.feature_importances = {
                    feature_names[i]: float(imps[i] / total) if total > 0 else 0.0
                    for i in range(len(feature_names))
                }

            logger.info(
                f"{model_type.value}: AUC={result.auc_roc:.3f}, "
                f"Acc={result.accuracy:.3f}, F1={result.f1_score:.3f}"
            )

        except Exception as e:
            logger.error(f"خطا در محاسبه متریک {model_type}: {e}")

        return result

    def _get_win_probability(self, predictions: Dict[ModelType, float]) -> float:
        if not predictions:
            return 0.5
        return float(np.mean(list(predictions.values())))

    def _get_recommendation(self, win_prob: float, is_reliable: bool) -> str:
        if not is_reliable:
            return "WAIT"
        if win_prob >= 0.75:
            return "STRONG_BUY"
        if win_prob >= 0.60:
            return "BUY"
        if win_prob <= 0.25:
            return "STRONG_SELL"
        if win_prob <= 0.40:
            return "SELL"
        return "WAIT"


# ════════════════════════════════════════════════════════════════════════════════
# Phase D — Unified ML Bridge
# ════════════════════════════════════════════════════════════════════════════════
from dataclasses import dataclass as _dc, field as _field
from datetime import datetime as _dt
from typing import Optional as _Opt


@_dc
class UnifiedTrainingResult:
    """
    نتیجه آموزش یکپارچه — superset هر دو TrainingResult.
    جایگزین هر دو:
      • intelligence/ml_engine.py::TrainingResult  (v1)
      • self_learning/training_pipeline.py::TrainingResult (v2)
    """
    # ── شناسه‌ها (از v2) ────────────────────────────────────────────────────────────────
    model_id:      str   = _field(default_factory=lambda: "")
    symbol:        str   = "ALL"
    version:       str   = "v1.0.0"
    trained_at:    _dt   = _field(default_factory=_dt.utcnow)
    # ── نوع مدل (از v1) ───────────────────────────────────────────────────────────────
    model_type: "ModelType" = None  # type: ignore[assignment]
    # ── متریک‌های ارزیابی (مشترک) ────────────────────────────────────────────────
    accuracy:      float = 0.0
    precision:     float = 0.0
    recall:        float = 0.0
    f1_score:      float = 0.0
    auc_roc:       float = 0.0
    train_auc:     float = 0.0
    val_auc:       float = 0.0
    test_auc:      float = 0.0
    cv_auc_mean:   float = 0.0
    cv_auc_std:    float = 0.0
    # ── اطلاعات dataset ──────────────────────────────────────────────────────────────
    training_samples:   int = 0
    validation_samples: int = 0
    total_samples:      int = 0
    train_samples:      int = 0
    test_samples:       int = 0
    win_rate:           float = 0.0
    feature_count:      int = 0
    # ── فایل‌های مدل ───────────────────────────────────────────────────────────────────
    model_path:    str = ""
    scaler_path:   str = ""
    metadata_path: str = ""
    # ── وضعیت ───────────────────────────────────────────────────────────────────────────
    is_reliable:    bool = False
    is_acceptable:  bool = False
    feature_importances: Dict[str, float] = _field(default_factory=dict)
    feature_importance:  Dict[str, float] = _field(default_factory=dict)
    feature_names:       List[str]        = _field(default_factory=list)

    @classmethod
    def from_v1(cls, v1: "TrainingResult") -> "UnifiedTrainingResult":
        """تبدیل از v1 TrainingResult به Unified."""
        return cls(
            model_type=v1.model_type,
            accuracy=v1.accuracy, precision=v1.precision,
            recall=v1.recall, f1_score=v1.f1_score,
            auc_roc=v1.auc_roc, train_auc=v1.auc_roc,
            training_samples=v1.training_samples,
            validation_samples=v1.validation_samples,
            total_samples=v1.training_samples + v1.validation_samples,
            feature_importances=v1.feature_importances,
            feature_importance=v1.feature_importances,
            is_reliable=v1.is_reliable, is_acceptable=v1.is_reliable,
        )

    @classmethod
    def from_v2(cls, v2: Any) -> "UnifiedTrainingResult":
        """تبدیل از v2 TrainingResult (self_learning) به Unified."""
        return cls(
            model_id=getattr(v2, 'model_id', ''),
            symbol=getattr(v2, 'symbol', 'ALL'),
            version=getattr(v2, 'version', 'v1.0.0'),
            trained_at=getattr(v2, 'trained_at', _dt.utcnow()),
            accuracy=getattr(v2, 'accuracy', 0.0),
            precision=getattr(v2, 'precision', 0.0),
            recall=getattr(v2, 'recall', 0.0),
            f1_score=getattr(v2, 'f1_score', 0.0),
            train_auc=getattr(v2, 'train_auc', 0.0),
            auc_roc=getattr(v2, 'train_auc', 0.0),
            val_auc=getattr(v2, 'val_auc', 0.0),
            test_auc=getattr(v2, 'test_auc', 0.0),
            cv_auc_mean=getattr(v2, 'cv_auc_mean', 0.0),
            cv_auc_std=getattr(v2, 'cv_auc_std', 0.0),
            total_samples=getattr(v2, 'total_samples', 0),
            train_samples=getattr(v2, 'train_samples', 0),
            test_samples=getattr(v2, 'test_samples', 0),
            win_rate=getattr(v2, 'win_rate', 0.0),
            feature_count=getattr(v2, 'feature_count', 0),
            model_path=getattr(v2, 'model_path', ''),
            scaler_path=getattr(v2, 'scaler_path', ''),
            metadata_path=getattr(v2, 'metadata_path', ''),
            is_acceptable=getattr(v2, 'is_acceptable', False),
            is_reliable=getattr(v2, 'is_acceptable', False),
            feature_importance=getattr(v2, 'feature_importance', {}),
            feature_importances=getattr(v2, 'feature_importance', {}),
            feature_names=getattr(v2, 'feature_names', []),
        )

    def to_v1_compat(self) -> "TrainingResult":
        """تبدیل به v1 TrainingResult برای backward compatibility."""
        r = TrainingResult(model_type=self.model_type or ModelType.XGBOOST)
        r.accuracy = self.accuracy
        r.precision = self.precision
        r.recall = self.recall
        r.f1_score = self.f1_score
        r.auc_roc = self.auc_roc or self.train_auc
        r.training_samples = self.training_samples or self.train_samples
        r.validation_samples = self.validation_samples or self.test_samples
        r.feature_importances = self.feature_importances or self.feature_importance
        r.is_reliable = self.is_reliable or self.is_acceptable
        return r


class UnifiedMLEngine:
    """
    موتور ML یکپارچه — پل بین v1 و v2.
    اولویت: self_learning/training_pipeline (v2) ← با persistence و versioning
    Fallback:  intelligence/ml_engine (v1)  ← اگر v2 در دسترس نبود
    """

    def __init__(self, model_dir: str = "models", symbol: str = "ALL") -> None:
        self._model_dir = model_dir
        self._symbol = symbol
        self._v1_engine: _Opt["MLEngine"] = None
        self._v2_pipeline: _Opt[Any] = None
        self._logger = get_logger("unified_ml_engine")
        try:
            from ..self_learning.training_pipeline import TrainingPipeline, TrainingConfig
            cfg = TrainingConfig(symbol=symbol, model_dir=model_dir)
            self._v2_pipeline = TrainingPipeline(cfg)
            self._logger.info(f"UnifiedMLEngine: v2 active for {symbol}")
        except Exception as e:
            self._logger.warning(f"UnifiedMLEngine: v2 unavailable ({e}), using v1")
            self._v1_engine = MLEngine(model_dir=model_dir)

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        """پیش‌بینی با اولویت v2."""
        if self._v1_engine is not None:
            return self._v1_engine.predict(features)
        return MLPrediction(
            win_probability=0.5, confidence=0.0, is_reliable=False,
            recommendation="WAIT", model_type=ModelType.XGBOOST,
            feature_importances={}, training_samples=0,
        )

    @property
    def using_v2(self) -> bool:
        return self._v2_pipeline is not None
