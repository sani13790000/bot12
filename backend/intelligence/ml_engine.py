"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: MLEngine — یادگیری ماشین

مدل‌ها:
  • XGBoost   ← gradient boosting سریع و دقیق
  • LightGBM  ← مناسب داده‌های بزرگ
  • CatBoost  ← مقاوم در برابر overfitting

قوانین:
  • سیستم فقط وزن‌ها را تنظیم می‌کند — هیچ استراتژی حذف نمی‌شود
  • یادگیری فقط بر اساس آمار قابل اطمینان انجام می‌شود
  • حداقل ۵۰ معامله برای آموزش اولیه نیاز است
  • حداقل ۲۰۰ معامله برای آموزش با اطمینان کافی
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

# حداقل تعداد معامله برای آموزش
MIN_TRADES_FOR_TRAINING = 50
MIN_TRADES_FOR_RELIABLE = 200


class ModelType(str, Enum):
    """نوع مدل ML"""
    XGBOOST = "XGBOOST"
    LIGHTGBM = "LIGHTGBM"
    CATBOOST = "CATBOOST"
    ENSEMBLE = "ENSEMBLE"  # ترکیب هر سه


@dataclass
class MLPrediction:
    """
    پیش‌بینی مدل ML برای یک سیگنال.
    """
    win_probability: float = 0.0        # احتمال برنده شدن (0-1)
    confidence: float = 0.0             # اطمینان مدل (0-1)
    model_type: ModelType = ModelType.ENSEMBLE
    feature_importances: Dict[str, float] = field(default_factory=dict)
    recommendation: str = ""             # STRONG_BUY / BUY / NEUTRAL / SKIP
    training_samples: int = 0           # تعداد نمونه آموزشی استفاده‌شده
    is_reliable: bool = False           # آیا پیش‌بینی قابل اعتماد است

    @property
    def adjusted_score(self) -> float:
        """
        امتیاز تنظیم‌شده بر اساس احتمال و اطمینان.
        برای ترکیب با Decision Engine استفاده می‌شود.
        """
        if not self.is_reliable:
            return 0.5  # neutral اگر داده کافی نداریم
        return self.win_probability * self.confidence


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

    مهم:
      این موتور فقط اطلاعات احتمالاتی تولید می‌کند.
      Decision Engine نهایی تصمیم می‌گیرد.
    """

    def __init__(self, model_dir: str = "models/ml") -> None:
        """
        Args:
            model_dir: مسیر ذخیره مدل‌های آموزش‌دیده
        """
        self._model_dir = model_dir
        self._models: Dict[ModelType, Any] = {}
        self._is_trained = False
        self._training_results: Dict[ModelType, TrainingResult] = {}
        self._feature_names: List[str] = []
        os.makedirs(model_dir, exist_ok=True)
        logger.info(f"MLEngine راه‌اندازی شد — model_dir: {model_dir}")

    def train(self, memory: TradeMemory) -> Dict[ModelType, TrainingResult]:
        """
        آموزش همه مدل‌ها روی تاریخچه معاملات.

        Args:
            memory: حافظه معاملاتی با context کامل

        Returns:
            نتایج آموزش برای هر مدل
        """
        features, labels = memory.to_feature_matrix()

        if len(features) < MIN_TRADES_FOR_TRAINING:
            logger.warning(
                f"داده کافی برای آموزش نیست: {len(features)} < {MIN_TRADES_FOR_TRAINING}"
            )
            return {}

        is_reliable = len(features) >= MIN_TRADES_FOR_RELIABLE
        if not is_reliable:
            logger.info(
                f"آموزش با داده محدود: {len(features)} معامله "
                f"(برای اطمینان کامل: {MIN_TRADES_FOR_RELIABLE})"
            )

        # استخراج feature names
        self._feature_names = list(features[0].keys())

        # تبدیل به numpy arrays
        X = np.array([[f[k] for k in self._feature_names] for f in features])
        y = np.array(labels)

        # تقسیم train/validation (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        results = {}

        # آموزش XGBoost
        results[ModelType.XGBOOST] = self._train_xgboost(
            X_train, y_train, X_val, y_val, is_reliable
        )

        # آموزش LightGBM
        results[ModelType.LIGHTGBM] = self._train_lightgbm(
            X_train, y_train, X_val, y_val, is_reliable
        )

        # آموزش CatBoost
        results[ModelType.CATBOOST] = self._train_catboost(
            X_train, y_train, X_val, y_val, is_reliable
        )

        self._training_results = results
        self._is_trained = True

        # لاگ خلاصه
        for model_type, result in results.items():
            logger.info(
                f"آموزش {model_type.value} | "
                f"Accuracy: {result.accuracy:.3f} | "
                f"AUC: {result.auc_roc:.3f} | "
                f"Samples: {result.training_samples}"
            )

        return results

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        """
        پیش‌بینی احتمال موفقیت یک سیگنال.

        Args:
            features: feature vector از TradeContext.to_ml_features()

        Returns:
            MLPrediction با احتمال و توصیه
        """
        if not self._is_trained:
            logger.debug("مدل آموزش ندیده — پیش‌بینی neutral")
            return MLPrediction(
                win_probability=0.5,
                confidence=0.0,
                recommendation="NEUTRAL",
                is_reliable=False,
            )

        # تبدیل به numpy array با ترتیب صحیح
        X = np.array([[features.get(k, 0.0) for k in self._feature_names]])

        predictions = {}
        for model_type, model in self._models.items():
            if model is not None:
                try:
                    prob = self._get_win_probability(model, model_type, X)
                    predictions[model_type] = prob
                except Exception as e:
                    logger.warning(f"خطا در پیش‌بینی {model_type.value}: {e}")

        if not predictions:
            return MLPrediction(win_probability=0.5, is_reliable=False)

        # Ensemble: میانگین وزنی بر اساس AUC آموزش
        weights = {}
        for mt, result in self._training_results.items():
            if mt in predictions:
                weights[mt] = result.auc_roc

        total_weight = sum(weights.values())
        if total_weight == 0:
            ensemble_prob = sum(predictions.values()) / len(predictions)
        else:
            ensemble_prob = sum(
                predictions[mt] * weights[mt] / total_weight
                for mt in predictions
            )

        # محاسبه اطمینان مدل (یکپارچگی پیش‌بینی‌ها)
        if len(predictions) > 1:
            probs = list(predictions.values())
            std = float(np.std(probs))
            confidence = max(0.1, 1.0 - std * 2)  # هر چه انحراف کمتر، اطمینان بیشتر
        else:
            confidence = 0.6

        # اطمینان را بر اساس تعداد داده آموزشی تنظیم می‌کنیم
        min_samples = min(
            r.training_samples for r in self._training_results.values()
        )
        is_reliable = min_samples >= MIN_TRADES_FOR_RELIABLE

        # تولید توصیه
        recommendation = self._get_recommendation(ensemble_prob, is_reliable)

        # feature importances از بهترین مدل
        best_model_type = max(
            self._training_results,
            key=lambda mt: self._training_results[mt].auc_roc,
        )
        importances = self._training_results[best_model_type].feature_importances

        return MLPrediction(
            win_probability=float(ensemble_prob),
            confidence=float(confidence),
            model_type=ModelType.ENSEMBLE,
            feature_importances=importances,
            recommendation=recommendation,
            training_samples=min_samples,
            is_reliable=is_reliable,
        )

    def save_models(self) -> None:
        """ذخیره مدل‌های آموزش‌دیده روی دیسک"""
        if not self._is_trained:
            return
        for model_type, model in self._models.items():
            if model is not None:
                path = os.path.join(self._model_dir, f"{model_type.value.lower()}.pkl")
                with open(path, "wb") as f:
                    pickle.dump(model, f)
        # ذخیره feature names
        meta_path = os.path.join(self._model_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump({"feature_names": self._feature_names}, f)
        logger.info(f"مدل‌ها ذخیره شدند: {self._model_dir}")

    def load_models(self) -> bool:
        """بارگذاری مدل‌های ذخیره‌شده از دیسک"""
        meta_path = os.path.join(self._model_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return False
        with open(meta_path) as f:
            meta = json.load(f)
        self._feature_names = meta["feature_names"]

        loaded = 0
        for model_type in ModelType:
            if model_type == ModelType.ENSEMBLE:
                continue
            path = os.path.join(self._model_dir, f"{model_type.value.lower()}.pkl")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._models[model_type] = pickle.load(f)
                loaded += 1

        self._is_trained = loaded > 0
        if self._is_trained:
            logger.info(f"{loaded} مدل بارگذاری شد از {self._model_dir}")
        return self._is_trained

    # ─── متدهای خصوصی آموزش ────────────────────────────────────

    def _train_xgboost(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        is_reliable: bool,
    ) -> TrainingResult:
        """آموزش مدل XGBoost"""
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.0,
                scale_pos_weight=1.0,
                eval_metric="auc",
                early_stopping_rounds=20,
                random_state=42,
                verbosity=0,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            self._models[ModelType.XGBOOST] = model

            # محاسبه متریک‌ها
            y_pred_proba = model.predict_proba(X_val)[:, 1]
            return self._calculate_metrics(
                ModelType.XGBOOST, y_val, y_pred_proba,
                model.feature_importances_, len(X_train), len(X_val), is_reliable
            )
        except ImportError:
            logger.warning("xgboost نصب نیست — از این مدل صرف‌نظر می‌شود")
            self._models[ModelType.XGBOOST] = None
            return TrainingResult(ModelType.XGBOOST)

    def _train_lightgbm(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        is_reliable: bool,
    ) -> TrainingResult:
        """آموزش مدل LightGBM"""
        try:
            import lightgbm as lgb
            model = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbose=-1,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
            self._models[ModelType.LIGHTGBM] = model

            y_pred_proba = model.predict_proba(X_val)[:, 1]
            return self._calculate_metrics(
                ModelType.LIGHTGBM, y_val, y_pred_proba,
                model.feature_importances_, len(X_train), len(X_val), is_reliable
            )
        except ImportError:
            logger.warning("lightgbm نصب نیست — از این مدل صرف‌نظر می‌شود")
            self._models[ModelType.LIGHTGBM] = None
            return TrainingResult(ModelType.LIGHTGBM)

    def _train_catboost(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        is_reliable: bool,
    ) -> TrainingResult:
        """آموزش مدل CatBoost"""
        try:
            from catboost import CatBoostClassifier, Pool
            model = CatBoostClassifier(
                iterations=200,
                depth=4,
                learning_rate=0.05,
                l2_leaf_reg=3.0,
                random_strength=1.0,
                bagging_temperature=1.0,
                od_type="Iter",
                od_wait=20,
                random_seed=42,
                verbose=False,
            )
            train_pool = Pool(X_train, y_train)
            val_pool = Pool(X_val, y_val)
            model.fit(train_pool, eval_set=val_pool)
            self._models[ModelType.CATBOOST] = model

            y_pred_proba = model.predict_proba(X_val)[:, 1]
            importances = model.get_feature_importance() / 100.0
            return self._calculate_metrics(
                ModelType.CATBOOST, y_val, y_pred_proba,
                importances, len(X_train), len(X_val), is_reliable
            )
        except ImportError:
            logger.warning("catboost نصب نیست — از این مدل صرف‌نظر می‌شود")
            self._models[ModelType.CATBOOST] = None
            return TrainingResult(ModelType.CATBOOST)

    def _calculate_metrics(
        self,
        model_type: ModelType,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        feature_importances: np.ndarray,
        train_samples: int,
        val_samples: int,
        is_reliable: bool,
    ) -> TrainingResult:
        """محاسبه متریک‌های ارزیابی مدل"""
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score,
            f1_score, roc_auc_score
        )

        y_pred = (y_pred_proba >= 0.5).astype(int)

        # feature importances به صورت normalize‌شده
        fi_total = feature_importances.sum()
        if fi_total > 0:
            fi_normalized = feature_importances / fi_total
        else:
            fi_normalized = feature_importances

        fi_dict = {
            name: float(imp)
            for name, imp in zip(self._feature_names, fi_normalized)
        }

        return TrainingResult(
            model_type=model_type,
            accuracy=float(accuracy_score(y_true, y_pred)),
            precision=float(precision_score(y_true, y_pred, zero_division=0)),
            recall=float(recall_score(y_true, y_pred, zero_division=0)),
            f1_score=float(f1_score(y_true, y_pred, zero_division=0)),
            auc_roc=float(roc_auc_score(y_true, y_pred_proba)),
            training_samples=train_samples,
            validation_samples=val_samples,
            feature_importances=fi_dict,
            is_reliable=is_reliable,
        )

    def _get_win_probability(
        self, model: Any, model_type: ModelType, X: np.ndarray
    ) -> float:
        """استخراج احتمال برنده شدن از مدل"""
        proba = model.predict_proba(X)[0]
        return float(proba[1])  # احتمال کلاس 1 (WIN)

    def _get_recommendation(self, win_prob: float, is_reliable: bool) -> str:
        """تولید توصیه بر اساس احتمال"""
        if not is_reliable:
            return "NEUTRAL"
        if win_prob >= 0.70:
            return "STRONG_BUY"
        elif win_prob >= 0.60:
            return "BUY"
        elif win_prob >= 0.45:
            return "NEUTRAL"
        else:
            return "SKIP"
