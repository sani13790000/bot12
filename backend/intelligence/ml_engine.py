"""ML Engine — Phase 5: Walk-Forward CV, Concept Drift Detection, Feature Importance."""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    direction: str  # BUY / SELL / NO_TRADE
    confidence: float  # 0.0 – 1.0
    risk_score: float  # 0.0 – 1.0
    should_trade: bool
    feature_importance: Dict[str, float] = field(default_factory=dict)
    model_version: str = "1.0"
    predicted_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def reliability_score(self) -> float:
        """Combined score used by VotingEngine."""
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
    overfit_ratio: float  # train_acc / test_acc — >1.15 is suspect


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
    avg_oos_accuracy: float = 0.0  # out-of-sample average
    avg_overfit_ratio: float = 1.0
    drift_status: DriftStatus = DriftStatus.STABLE
    drift_score: float = 0.0
    trained_at: datetime = field(default_factory=datetime.utcnow)
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
    """Page-Hinkley test for concept drift detection."""

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
        # Exponential moving average
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

    # ------------------------------------------------------------------ #
    #  PUBLIC API
    # ------------------------------------------------------------------ #

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        """Run inference. Returns NO_TRADE if model not ready."""
        if not self._is_trained or self._direction_model is None:
            return MLPrediction(
                direction="NO_TRADE",
                confidence=0.5,
                risk_score=0.5,
                should_trade=False,
                model_version=self._model_version,
            )

        try:
            X = self._build_feature_vector(features)
            X_scaled = self._scaler.transform([X])

            direction_proba = self._direction_model.predict_proba(X_scaled)[0]
            direction_idx = int(direction_proba.argmax())
            direction_labels = ["BUY", "NO_TRADE", "SELL"]
            direction = direction_labels[direction_idx]
            direction_conf = float(direction_proba[direction_idx])

            risk_proba = self._risk_model.predict_proba(X_scaled)[0]
            risk_score = float(risk_proba[-1])  # probability of HIGH risk

            conf_proba = self._confidence_model.predict_proba(X_scaled)[0]
            confidence = float(conf_proba[-1])  # probability of HIGH confidence

            importance = self._get_feature_importance()
            should_trade = (
                direction in ("BUY", "SELL")
                and direction_conf >= self.RELIABILITY_THRESHOLD
                and risk_score < 0.6
            )

            # Update drift detector
            drift_status = self._drift_detector.update(direction_conf)
            if drift_status == DriftStatus.DRIFTED:
                logger.warning("[MLEngine] Concept drift detected — recommend retrain")

            self._prediction_history.append(direction_conf)

            return MLPrediction(
                direction=direction,
                confidence=confidence,
                risk_score=risk_score,
                should_trade=should_trade,
                feature_importance=importance,
                model_version=self._model_version,
            )

        except Exception as exc:
            logger.error("[MLEngine] predict error: %s", exc)
            return MLPrediction(
                direction="NO_TRADE",
                confidence=0.5,
                risk_score=0.5,
                should_trade=False,
                model_version=self._model_version,
            )

    def train(self, trade_contexts: List[Any]) -> TrainingResult:
        """Train with walk-forward cross-validation."""
        if len(trade_contexts) < self.MIN_TRAIN_SAMPLES:
            return TrainingResult(
                success=False,
                model_type=ModelType.DIRECTION,
                accuracy=0.0,
                f1_score=0.0,
                n_samples=len(trade_contexts),
                feature_names=[],
                feature_importance={},
                error=f"Need >= {self.MIN_TRAIN_SAMPLES} samples, got {len(trade_contexts)}",
            )

        try:
            X, y_dir, y_risk, y_conf, feat_names = self._build_dataset(trade_contexts)
            self._feature_names = feat_names

            # Walk-forward cross-validation (time-ordered, no shuffle)
            wf_folds = self._walk_forward_cv(X, y_dir)
            avg_oos = statistics.mean(f.test_accuracy for f in wf_folds) if wf_folds else 0.0
            avg_overfit = statistics.mean(f.overfit_ratio for f in wf_folds) if wf_folds else 1.0

            # Final training on ALL data
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

            # Accuracy on full set (in-sample)
            from sklearn.metrics import accuracy_score, f1_score
            y_pred = self._direction_model.predict(X_scaled)
            acc = float(accuracy_score(y_dir, y_pred))
            f1 = float(f1_score(y_dir, y_pred, average="weighted", zero_division=0))

            importance = self._get_feature_importance()

            # Drift check
            drift_status = DriftStatus.STABLE
            drift_score = 0.0
            if self._prediction_history:
                recent = self._prediction_history[-30:]
                older = self._prediction_history[-60:-30]
                if len(older) >= 10 and len(recent) >= 10:
                    shift = abs(statistics.mean(recent) - statistics.mean(older))
                    drift_score = shift
                    if shift > 0.15:
                        drift_status = DriftStatus.DRIFTED
                    elif shift > 0.08:
                        drift_status = DriftStatus.WARNING

            self._is_trained = True
            self._last_trained = datetime.utcnow()

            # Increment version
            try:
                major, minor = self._model_version.split(".")
                self._model_version = f"{major}.{int(minor) + 1}"
            except Exception:
                self._model_version = "1.1"

            self._save_models()

            return TrainingResult(
                success=True,
                model_type=ModelType.DIRECTION,
                accuracy=acc,
                f1_score=f1,
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

        except ImportError:
            return TrainingResult(
                success=False,
                model_type=ModelType.DIRECTION,
                accuracy=0.0,
                f1_score=0.0,
                n_samples=len(trade_contexts),
                feature_names=[],
                feature_importance={},
                error="scikit-learn not installed",
            )
        except Exception as exc:
            logger.error("[MLEngine] train error: %s", exc)
            return TrainingResult(
                success=False,
                model_type=ModelType.DIRECTION,
                accuracy=0.0,
                f1_score=0.0,
                n_samples=len(trade_contexts),
                feature_names=[],
                feature_importance={},
                error=str(exc),
            )

    def save_models(self) -> bool:
        return self._save_models()

    def load_models(self) -> bool:
        return self._try_load_models()

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def drift_status(self) -> DriftStatus:
        return self._drift_detector.update.__self__._history and DriftStatus.STABLE or DriftStatus.STABLE

    def get_drift_info(self) -> Dict[str, Any]:
        return {
            "drift_score": self._drift_detector.drift_score(),
            "recent_mean_confidence": self._drift_detector.recent_mean(),
            "prediction_count": len(self._prediction_history),
            "last_trained": self._last_trained.isoformat() if self._last_trained else None,
            "model_version": self._model_version,
        }

    def should_retrain(self) -> bool:
        """True if concept drift or model is stale (>24h)."""
        if not self._is_trained:
            return True
        drift = self._drift_detector.drift_score()
        if drift > 0.5:
            return True
        if self._last_trained and datetime.utcnow() - self._last_trained > timedelta(hours=24):
            return True
        return False

    # ------------------------------------------------------------------ #
    #  WALK-FORWARD CV
    # ------------------------------------------------------------------ #

    def _walk_forward_cv(self, X: List, y: List) -> List[WalkForwardFold]:
        """Time-series walk-forward cross-validation — NO shuffling."""
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.metrics import accuracy_score, f1_score
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return []

        n = len(X)
        min_train = max(self.MIN_TRAIN_SAMPLES, n // (self.WALK_FORWARD_SPLITS + 1))
        folds: List[WalkForwardFold] = []

        for i in range(self.WALK_FORWARD_SPLITS):
            train_end = min_train + i * (n - min_train) // self.WALK_FORWARD_SPLITS
            test_end = min(train_end + max(10, (n - min_train) // self.WALK_FORWARD_SPLITS), n)

            if train_end >= test_end or train_end < 20:
                continue

            X_train, y_train = X[:train_end], y[:train_end]
            X_test, y_test = X[train_end:test_end], y[train_end:test_end]

            if len(set(y_train)) < 2 or len(X_test) < 5:
                continue

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_train)
            X_te_s = scaler.transform(X_test)

            model = GradientBoostingClassifier(
                n_estimators=60, max_depth=3, learning_rate=0.1, random_state=42
            )
            model.fit(X_tr_s, y_train)

            train_acc = float(accuracy_score(y_train, model.predict(X_tr_s)))
            test_acc = float(accuracy_score(y_test, model.predict(X_te_s)))
            train_f1 = float(f1_score(y_train, model.predict(X_tr_s), average="weighted", zero_division=0))
            test_f1 = float(f1_score(y_test, model.predict(X_te_s), average="weighted", zero_division=0))
            overfit = train_acc / max(test_acc, 0.01)

            folds.append(WalkForwardFold(
                fold_index=i,
                train_size=train_end,
                test_size=test_end - train_end,
                train_accuracy=train_acc,
                test_accuracy=test_acc,
                train_f1=train_f1,
                test_f1=test_f1,
                overfit_ratio=overfit,
            ))

        return folds

    # ------------------------------------------------------------------ #
    #  DATASET BUILDER
    # ------------------------------------------------------------------ #

    def _build_dataset(
        self, contexts: List[Any]
    ) -> Tuple[List[List[float]], List[int], List[int], List[int], List[str]]:
        """Convert TradeContext list to feature matrix. Time-ordered, NO shuffle."""
        feature_names = [
            "pnl_pips", "realized_rr", "confidence_score", "duration_minutes",
            "previous_consecutive_losses", "news_active",
            "smc_ob_count", "smc_fvg_count", "smc_liquidity",
            "pa_pin_bar", "pa_engulfing", "pa_inside_bar",
            "session_asian", "session_london", "session_ny",
        ]

        X, y_dir, y_risk, y_conf = [], [], [], []

        for ctx in contexts:
            try:
                pnl = float(getattr(ctx, "pnl_pips", 0) or 0)
                rr = float(getattr(ctx, "realized_rr", 0) or 0)
                score = float(getattr(ctx, "confidence_score", 50) or 50) / 100.0
                dur = float(getattr(ctx, "duration_minutes", 0) or 0)
                consec = float(getattr(ctx, "previous_consecutive_losses", 0) or 0)
                news = 1.0 if getattr(ctx, "news_active", False) else 0.0

                smc = getattr(ctx, "smc", {}) or {}
                ob = float(smc.get("order_blocks", 0))
                fvg = float(smc.get("fvg_count", 0))
                liq = float(smc.get("liquidity_score", 0))

                pa = getattr(ctx, "price_action", {}) or {}
                pin = 1.0 if pa.get("pin_bar") else 0.0
                eng = 1.0 if pa.get("engulfing") else 0.0
                ins = 1.0 if pa.get("inside_bar") else 0.0

                sess = str(getattr(ctx, "session", "") or "").upper()
                s_as = 1.0 if "ASIAN" in sess else 0.0
                s_lo = 1.0 if "LONDON" in sess else 0.0
                s_ny = 1.0 if "NEW_YORK" in sess or "NY" in sess else 0.0

                X.append([pnl, rr, score, dur, consec, news, ob, fvg, liq, pin, eng, ins, s_as, s_lo, s_ny])

                outcome = str(getattr(ctx, "outcome", "") or "").upper()
                direction = str(getattr(ctx, "direction", "") or "").upper()

                if outcome in ("WIN", "PROFIT", "TP"):
                    y_dir.append(0 if "BUY" in direction else 2)
                    y_risk.append(0)  # LOW
                    y_conf.append(2)  # HIGH
                elif outcome in ("LOSS", "SL", "STOP"):
                    y_dir.append(1)   # NO_TRADE in hindsight
                    y_risk.append(2)  # HIGH
                    y_conf.append(0)  # LOW
                else:
                    y_dir.append(1)   # NO_TRADE
                    y_risk.append(1)  # MEDIUM
                    y_conf.append(1)  # MEDIUM

            except Exception:
                continue

        return X, y_dir, y_risk, y_conf, feature_names

    # ------------------------------------------------------------------ #
    #  HELPERS
    # ------------------------------------------------------------------ #

    def _build_feature_vector(self, features: Dict[str, float]) -> List[float]:
        return [
            features.get("pnl_pips", 0.0),
            features.get("realized_rr", 0.0),
            features.get("confidence_score", 0.5),
            features.get("duration_minutes", 0.0),
            features.get("previous_consecutive_losses", 0.0),
            features.get("news_active", 0.0),
            features.get("smc_ob_count", 0.0),
            features.get("smc_fvg_count", 0.0),
            features.get("smc_liquidity", 0.0),
            features.get("pa_pin_bar", 0.0),
            features.get("pa_engulfing", 0.0),
            features.get("pa_inside_bar", 0.0),
            features.get("session_asian", 0.0),
            features.get("session_london", 0.0),
            features.get("session_ny", 0.0),
        ]

    def _get_feature_importance(self) -> Dict[str, float]:
        if self._direction_model is None or not self._feature_names:
            return {}
        try:
            imp = self._direction_model.feature_importances_
            return {n: round(float(v), 4) for n, v in zip(self._feature_names, imp)}
        except Exception:
            return {}

    def _save_models(self) -> bool:
        try:
            import pickle
            (self.model_dir / "direction_model.pkl").write_bytes(pickle.dumps(self._direction_model))
            (self.model_dir / "confidence_model.pkl").write_bytes(pickle.dumps(self._confidence_model))
            (self.model_dir / "risk_model.pkl").write_bytes(pickle.dumps(self._risk_model))
            (self.model_dir / "scaler.pkl").write_bytes(pickle.dumps(self._scaler))
            (self.model_dir / "version.txt").write_text(self._model_version)
            (self.model_dir / "features.txt").write_text("\n".join(self._feature_names))
            logger.info("[MLEngine] models saved v%s", self._model_version)
            return True
        except Exception as exc:
            logger.error("[MLEngine] save error: %s", exc)
            return False

    def _try_load_models(self) -> bool:
        try:
            import pickle
            d = self.model_dir
            if not (d / "direction_model.pkl").exists():
                return False
            self._direction_model = pickle.loads((d / "direction_model.pkl").read_bytes())
            self._confidence_model = pickle.loads((d / "confidence_model.pkl").read_bytes())
            self._risk_model = pickle.loads((d / "risk_model.pkl").read_bytes())
            self._scaler = pickle.loads((d / "scaler.pkl").read_bytes())
            if (d / "version.txt").exists():
                self._model_version = (d / "version.txt").read_text().strip()
            if (d / "features.txt").exists():
                self._feature_names = (d / "features.txt").read_text().strip().splitlines()
            self._is_trained = True
            logger.info("[MLEngine] loaded v%s", self._model_version)
            return True
        except Exception as exc:
            logger.warning("[MLEngine] load skipped: %s", exc)
            return False


# ------------------------------------------------------------------ #
#  UNIFIED BRIDGE (backward compat)
# ------------------------------------------------------------------ #

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
                logger.warning("[UnifiedMLEngine] v2 train failed: %s — falling back to v1", exc)
        return self._v1.train(contexts)

    def predict(self, features: Dict[str, float]) -> MLPrediction:
        # Always use v1 for inference (consistent feature vector)
        return self._v1.predict(features)

    def should_retrain(self) -> bool:
        return self._v1.should_retrain()

    def get_drift_info(self) -> Dict[str, Any]:
        return self._v1.get_drift_info()

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
