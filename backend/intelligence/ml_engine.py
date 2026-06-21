"""ML Engine — Phase 5: Walk-Forward CV, Concept Drift Detection, Feature Importance."""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    DIRECTION = "direction"
    CONFIDENCE = "confidence"
    RISK = "risk"


class DriftStatus(str, Enum):
    STABLE = "stable"
    WARNING = "warning"
    DRIFTED = "drifted"


@dataclass
class MLPrediction:
    direction: str
    confidence: float
    risk_score: float
    should_trade: bool
    feature_importance: Dict[str, float] = field(default_factory=dict)
    model_version: str = "1.0"
    # FIX TECH-6: utcnow() deprecated -> timezone-aware lambda
    predicted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def reliability_score(self) -> float:
        return round(self.confidence * (1.0 - self.risk_score), 4)


@dataclass
class WalkForwardFold:
    fold_index: int
    train_size: int
    test_size: int
    train_accuracy: float
    test_accuracy: float
    train_f1: float
    test_f1: float
    overfit_ratio: float


@dataclass
class TrainingResult:
    success: bool
    model_type: ModelType
    accuracy: float
    f1_score: float
    n_samples: int
    feature_names: List[str]
    feature_importance: Dict[str, float]
    walk_forward_folds: List[WalkForwardFold] = field(default_factory=list)
    avg_oos_accuracy: float = 0.0
    avg_overfit_ratio: float = 1.0
    drift_status: DriftStatus = DriftStatus.STABLE
    drift_score: float = 0.0
    # FIX TECH-6: timezone-aware
    trained_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
    model_version: str = "1.0"

    def summary(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error})"
        drift = f" drift={self.drift_status.value}({self.drift_score:.3f})" if self.drift_score > 0 else ""
        wf = f" oos={self.avg_oos_accuracy:.3f}" if self.avg_oos_accuracy > 0 else ""
        return (
            f"[MLEngine] {self.model_type.value} {status} "
            f"acc={self.accuracy:.3f} f1={self.f1_score:.3f} "
            f"n={self.n_samples}{wf}{drift} v{self.model_version}"
        )


class ConceptDriftDetector:
    def __init__(self, delta: float = 0.005, threshold: float = 50.0, alpha: float = 0.9999):
        self.delta = delta
        self.threshold = threshold
        self.alpha = alpha
        self._cum_sum = 0.0
        self._min_sum = 0.0
        self._mean = 0.0
        self._n = 0
        self._history: List[float] = []

    def update(self, value: float) -> DriftStatus:
        self._n += 1
        self._history.append(value)
        if self._n == 1:
            self._mean = value
        else:
            self._mean = self.alpha * self._mean + (1 - self.alpha) * value
        self._cum_sum += value - self._mean - self.delta
        self._min_sum = min(self._min_sum, self._cum_sum)
        ph_stat = self._cum_sum - self._min_sum
        if ph_stat > self.threshold:
            self.reset()
            return DriftStatus.DRIFTED
        if ph_stat > self.threshold * 0.5:
            return DriftStatus.WARNING
        return DriftStatus.STABLE

    def reset(self) -> None:
        self._cum_sum = 0.0
        self._min_sum = 0.0

    def drift_score(self) -> float:
        return max(0.0, self._cum_sum - self._min_sum) / max(self.threshold, 1.0)

    def recent_mean(self, window: int = 20) -> float:
        if not self._history:
            return 0.0
        tail = self._history[-window:]
        return sum(tail) / len(tail)


class MLEngine:
    """Production ML engine with walk-forward CV and concept drift detection."""

    N_FEATURES = 15
    WALK_FORWARD_SPLITS = 5
    MIN_TRAIN_SAMPLES = 50
    RELIABILITY_THRESHOLD = 0.45
    MODEL_DIR = Path("models")

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or self.MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._direction_model: Optional[Any] = None
        self._confidence_model: Optional[Any] = None
        self._risk_model: Optional[Any] = None
        self._scaler: Optional[Any] = None
        self._feature_names: List[str] = []
        self._is_trained = False
        self._model_version = "1.0"
        self._drift_detector = ConceptDriftDetector()
        self._prediction_history: List[float] = []
        self._last_trained: Optional[datetime] = None
        self._try_load_models()

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        if not self._is_trained or self._direction_model is None:
            return MLPrediction(
                direction="NO_TRADE", confidence=0.5, risk_score=0.5,
                should_trade=False, model_version=self._model_version,
            )
        try:
            fv = self._build_feature_vector(features)
            from sklearn.preprocessing import StandardScaler
            if self._scaler is not None:
                import numpy as np
                fv_scaled = self._scaler.transform([fv])[0]
            else:
                fv_scaled = fv
            dir_pred = self._direction_model.predict([fv_scaled])[0]
            dir_proba = self._direction_model.predict_proba([fv_scaled])[0]
            conf = float(max(dir_proba))
            risk = 0.5
            if self._risk_model is not None:
                risk_proba = self._risk_model.predict_proba([fv_scaled])[0]
                risk = float(max(risk_proba))
            direction = ["BUY", "NO_TRADE", "SELL"][int(dir_pred)] if dir_pred in (0, 1, 2) else "NO_TRADE"
            should_trade = direction in ("BUY", "SELL") and conf >= self.RELIABILITY_THRESHOLD
            drift_status = self._drift_detector.update(conf)
            self._prediction_history.append(conf)
            if len(self._prediction_history) > 500:
                self._prediction_history = self._prediction_history[-500:]
            importance = self._get_feature_importance()
            return MLPrediction(
                direction=direction,
                confidence=conf,
                risk_score=risk,
                should_trade=should_trade,
                feature_importance=importance,
                model_version=self._model_version,
            )
        except Exception as exc:
            logger.warning("predict failed: %s", exc)
            return MLPrediction(
                direction="NO_TRADE", confidence=0.5, risk_score=0.5,
                should_trade=False, model_version=self._model_version,
            )

    def train(self, trade_contexts: List[Any]) -> TrainingResult:
        if len(trade_contexts) < self.MIN_TRAIN_SAMPLES:
            return TrainingResult(
                success=False, model_type=ModelType.DIRECTION,
                accuracy=0.0, f1_score=0.0, n_samples=len(trade_contexts),
                feature_names=[], feature_importance={},
                error=f"Need >= {self.MIN_TRAIN_SAMPLES} samples, got {len(trade_contexts)}",
            )
        try:
            X, y_dir, y_risk, y_conf, feat_names = self._build_dataset(trade_contexts)
            self._feature_names = feat_names
            wf_folds = self._walk_forward_cv(X, y_dir)
            avg_oos = statistics.mean(f.test_accuracy for f in wf_folds) if wf_folds else 0.0
            avg_overfit = statistics.mean(f.overfit_ratio for f in wf_folds) if wf_folds else 1.0
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            self._scaler = StandardScaler()
            X_scaled = self._scaler.fit_transform(X)
            self._direction_model = GradientBoostingClassifier(
                n_estimators=120, max_depth=4, learning_rate=0.08,
                subsample=0.8, min_samples_leaf=5, random_state=42
            )
            self._direction_model.fit(X_scaled, y_dir)
            self._risk_model = GradientBoostingClassifier(
                n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42
            )
            self._risk_model.fit(X_scaled, y_risk)
            self._confidence_model = GradientBoostingClassifier(
                n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42
            )
            self._confidence_model.fit(X_scaled, y_conf)
            from sklearn.metrics import accuracy_score, f1_score
            y_pred = self._direction_model.predict(X_scaled)
            acc = float(accuracy_score(y_dir, y_pred))
            f1 = float(f1_score(y_dir, y_pred, average="weighted", zero_division=0))
            importance = self._get_feature_importance()
            drift_status = DriftStatus.STABLE
            drift_score = 0.0
            if self._prediction_history:
                recent = self._prediction_history[-30:]
                if len(recent) >= 10:
                    ds = self._drift_detector.update(statistics.mean(recent))
                    drift_status = ds
                    drift_score = self._drift_detector.drift_score()
            self._is_trained = True
            self._last_trained = datetime.now(timezone.utc)
            import uuid
            self._model_version = str(uuid.uuid4())[:8]
            self._save_models()
            return TrainingResult(
                success=True, model_type=ModelType.DIRECTION,
                accuracy=acc, f1_score=f1,
                n_samples=len(trade_contexts),
                feature_names=feat_names,
                feature_importance=importance,
                walk_forward_folds=wf_folds,
                avg_oos_accuracy=avg_oos,
                avg_overfit_ratio=avg_overfit,
                drift_status=drift_status,
                drift_score=drift_score,
                model_version=self._model_version,
            )
        except Exception as exc:
            logger.error("train failed: %s", exc, exc_info=True)
            return TrainingResult(
                success=False, model_type=ModelType.DIRECTION,
                accuracy=0.0, f1_score=0.0,
                n_samples=len(trade_contexts),
                feature_names=[], feature_importance={},
                error=str(exc),
            )

    async def async_train(self, trade_contexts: List[Any]) -> TrainingResult:
        """
        TECH-4 FIX: async wrapper — sklearn training runs in executor
        so it never blocks the event loop during trading execution.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.train, trade_contexts)

    async def async_predict(self, features: Dict[str, float]) -> MLPrediction:
        """Non-blocking predict wrapper."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.predict, features)

    def save_models(self) -> bool:
        return self._save_models()

    def load_models(self) -> bool:
        return self._try_load_models()

    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def drift_status(self) -> DriftStatus:
        return self._drift_detector.update(0.0) if not self._prediction_history else DriftStatus.STABLE

    def get_drift_info(self) -> Dict[str, Any]:
        return {
            "drift_score": self._drift_detector.drift_score(),
            "recent_mean": self._drift_detector.recent_mean(),
            "n_predictions": len(self._prediction_history),
            "last_trained": self._last_trained.isoformat() if self._last_trained else None,
        }

    def should_retrain(self) -> bool:
        if not self._is_trained:
            return True
        if self._last_trained is None:
            return True
        hours_since = (datetime.now(timezone.utc) - self._last_trained).total_seconds() / 3600
        if hours_since > 24:
            return True
        if self._drift_detector.drift_score() > 0.7:
            return True
        if len(self._prediction_history) > 100:
            recent = self._prediction_history[-20:]
            if statistics.mean(recent) < 0.35:
                return True
        return False

    def _walk_forward_cv(self, X: List, y: List) -> List[WalkForwardFold]:
        n = len(X)
        if n < self.WALK_FORWARD_SPLITS * 2:
            return []
        folds = []
        split_size = n // (self.WALK_FORWARD_SPLITS + 1)
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.metrics import accuracy_score, f1_score as f1_metric
            import numpy as np
        except ImportError:
            return []
        for i in range(self.WALK_FORWARD_SPLITS):
            train_end = split_size * (i + 1)
            test_end = min(train_end + split_size, n)
            if test_end <= train_end:
                continue
            X_train, y_train = X[:train_end], y[:train_end]
            X_test,  y_test  = X[train_end:test_end], y[train_end:test_end]
            if len(set(y_train)) < 2:
                continue
            try:
                clf = GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=42)
                clf.fit(X_train, y_train)
                tr_acc = float(accuracy_score(y_train, clf.predict(X_train)))
                te_acc = float(accuracy_score(y_test,  clf.predict(X_test)))
                tr_f1  = float(f1_metric(y_train, clf.predict(X_train), average="weighted", zero_division=0))
                te_f1  = float(f1_metric(y_test,  clf.predict(X_test),  average="weighted", zero_division=0))
                folds.append(WalkForwardFold(
                    fold_index=i, train_size=train_end, test_size=test_end - train_end,
                    train_accuracy=tr_acc, test_accuracy=te_acc,
                    train_f1=tr_f1, test_f1=te_f1,
                    overfit_ratio=tr_acc / max(te_acc, 0.001),
                ))
            except Exception as exc:
                logger.debug("WF fold %d failed: %s", i, exc)
        return folds

    def _build_dataset(
        self, contexts: List[Any]
    ) -> Tuple[List, List, List, List, List[str]]:
        X, y_dir, y_risk, y_conf, names = [], [], [], [], []
        for ctx in contexts:
            if not isinstance(ctx, dict):
                ctx = vars(ctx) if hasattr(ctx, "__dict__") else {}
            features = ctx.get("features", ctx)
            fv = self._build_feature_vector(features)
            outcome = ctx.get("outcome", ctx.get("result", "NO_TRADE"))
            dir_label = {"BUY": 0, "WIN": 0, "SELL": 2, "LOSS": 1, "NO_TRADE": 1}.get(
                str(outcome).upper(), 1
            )
            y_dir.append(dir_label)
            y_risk.append(0 if dir_label != 1 else 1)
            y_conf.append(0 if dir_label != 1 else 1)
            X.append(fv)
        if not names:
            names = [f"f{i}" for i in range(self.N_FEATURES)]
        return X, y_dir, y_risk, y_conf, names

    def _build_feature_vector(self, features: Dict[str, float]) -> List[float]:
        keys = [
            "smc_score", "pa_score", "mtf_score", "liquidity_score", "risk_score",
            "session_score", "volatility", "spread", "atr", "volume_ratio",
            "hour_of_day", "day_of_week", "trend_strength", "momentum", "rsi",
        ]
        fv = [float(features.get(k, 0.0)) for k in keys]
        while len(fv) < self.N_FEATURES:
            fv.append(0.0)
        return fv[:self.N_FEATURES]

    def _get_feature_importance(self) -> Dict[str, float]:
        if self._direction_model is None or not self._feature_names:
            return {}
        try:
            imp = self._direction_model.feature_importances_
            return dict(zip(self._feature_names, [float(x) for x in imp]))
        except Exception:
            return {}

    def _save_models(self) -> bool:
        try:
            import pickle
            data = {
                "direction": self._direction_model,
                "risk": self._risk_model,
                "confidence": self._confidence_model,
                "scaler": self._scaler,
                "feature_names": self._feature_names,
                "version": self._model_version,
            }
            path = self.model_dir / "ml_engine_v1.pkl"
            with open(path, "wb") as f:
                pickle.dump(data, f)
            return True
        except Exception as exc:
            logger.warning("_save_models failed: %s", exc)
            return False

    def _try_load_models(self) -> bool:
        try:
            import pickle
            path = self.model_dir / "ml_engine_v1.pkl"
            if not path.exists():
                return False
            with open(path, "rb") as f:
                data = pickle.load(f)
            self._direction_model = data.get("direction")
            self._risk_model      = data.get("risk")
            self._confidence_model= data.get("confidence")
            self._scaler          = data.get("scaler")
            self._feature_names   = data.get("feature_names", [])
            self._model_version   = data.get("version", "1.0")
            self._is_trained = self._direction_model is not None
            if self._is_trained:
                logger.info("MLEngine loaded v%s", self._model_version)
            return self._is_trained
        except Exception as exc:
            logger.warning("_try_load_models failed: %s", exc)
            return False


class UnifiedMLEngine:
    """Bridge: tries TrainingPipeline (v2) first, falls back to MLEngine (v1)."""

    def __init__(self, model_dir: Optional[Path] = None):
        self._v1 = MLEngine(model_dir=model_dir)
        self._v2: Optional[Any] = None
        self._use_v2 = False
        self._init_v2(model_dir)

    def _init_v2(self, model_dir: Optional[Path]) -> None:
        try:
            from backend.self_learning.training_pipeline import TrainingPipeline
            self._v2 = TrainingPipeline(model_dir=model_dir or Path("models"))
            self._use_v2 = True
            logger.info("[UnifiedMLEngine] using TrainingPipeline v2")
        except Exception as exc:
            logger.info("[UnifiedMLEngine] v2 unavailable (%s), using MLEngine v1", exc)

    def train(self, contexts: List[Any]) -> TrainingResult:
        if self._use_v2 and self._v2 is not None:
            try:
                result = self._v2.train(contexts)
                if result and getattr(result, "success", False):
                    return self._adapt_v2_result(result)
            except Exception as exc:
                logger.warning("[UnifiedMLEngine] v2 train failed: %s — falling back", exc)
        return self._v1.train(contexts)

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        return self._v1.predict(features)

    def should_retrain(self) -> bool:
        return self._v1.should_retrain()

    def get_drift_info(self) -> Dict[str, Any]:
        return self._v1.get_drift_info()

    async def async_train(self, contexts: List[Any]) -> TrainingResult:
        """
        TECH-4 FIX: async wrapper — sklearn training in executor.
        Prevents blocking the event loop during live trading.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.train, contexts)

    async def async_predict(self, features: Dict[str, float]) -> MLPrediction:
        """Non-blocking predict wrapper."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.predict, features)

    def _adapt_v2_result(self, v2_result: Any) -> TrainingResult:
        return TrainingResult(
            success=getattr(v2_result, "success", True),
            model_type=ModelType.DIRECTION,
            accuracy=getattr(v2_result, "accuracy", 0.0),
            f1_score=getattr(v2_result, "f1_score", 0.0),
            n_samples=getattr(v2_result, "n_samples", 0),
            feature_names=getattr(v2_result, "feature_names", []),
            feature_importance=getattr(v2_result, "feature_importance", {}),
            model_version=getattr(v2_result, "model_version", "2.0"),
        )
