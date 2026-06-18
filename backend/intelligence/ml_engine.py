"""
Galaxy Vast AI Trading Platform
════════════════════════════════
ML Engine — Unified Machine Learning Interface
ms’eooliyat: bridge €€ intelligence/ and self_learning/
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..core.logger import get_logger

logger = get_logger("intelligence.ml_engine")


class ModelType(str, Enum):
    DIRECTION  = "DIRECTION"
    CONFIDENCE = "CONFIDENCE"
    RISK       = "RISK"


@dataclass
class TrainingResult:
    model_type:    ModelType    = ModelType.DIRECTION
    auc_roc:       float        = 0.0
    accuracy:      float        = 0.0
    precision:     float        = 0.0
    recall:        float        = 0.0
    f1:            float        = 0.0
    train_samples: int          = 0
    test_samples:  int          = 0
    feature_names: List[str]    = field(default_factory=list)
    trained_at:    datetime     = field(default_factory=datetime.utcnow)
    model_path:    str          = ""
    is_acceptable: bool        = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type":    self.model_type.value,
            "auc_roc":       self.auc_roc,
            "accuracy":      self.accuracy,
            "precision":     self.precision,
            "recall":        self.recall,
            "f1":            self.f1,
            "train_samples": self.train_samples,
            "test_samples":  self.test_samples,
            "feature_names": self.feature_names,
            "trained_at":    self.trained_at.isoformat(),
            "model_path":    self.model_path,
            "is_acceptable": self.is_acceptable,
        }


class MLEngine:
    DEFAULT_MODEL_DIR = Path("models/ml_engine")

    def __init__(self, model_dir: Optional[Path] = None) -> None:
        self._model_dir   = model_dir or self.DEFAULT_MODEL_DIR
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._models:  Dict[ModelType, Any]             = {}
        self._scalers: Dict[ModelType, Any]             = {}
        self._results: Dict[ModelType, TrainingResult]  = {}
        logger.info(f"MLEngine v1 init | model_dir={self._model_dir}")

    def train(self, memory: Any) -> Dict[ModelType, TrainingResult]:
        results: Dict[ModelType, TrainingResult] = {}
        try:
            from sklearn.ensemble import GradientBoostingClassifier  # noqa
            from sklearn.preprocessing import StandardScaler  # noqa
        except ImportError:
            logger.warning("scikit-learn not available - skipping")
            return results
        trades = memory.get_recent(500) if hasattr(memory, "get_recent") else []
        if len(trades) < 30:
            logger.warning(f"Not enough trades: {len(trades)} < 30")
            return results
        try:
            features, labels = self._extract_features(trades)
        except Exception as exc:
            logger.error(f"Feature extraction failed: {exc}")
            return results
        if len(features) < 20:
            return results
        X = np.array(features, dtype=np.float32)
        y = np.array(labels,   dtype=np.int32)
        try:
            result = self._train_single(X, y, ModelType.DIRECTION)
            if result:
                results[ModelType.DIRECTION] = result
                self._results[ModelType.DIRECTION] = result
        except Exception as exc:
            logger.error(f"Direction model failed: {exc}")
        return results

    def _train_single(self, X, y, model_type):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import roc_auc_score, accuracy_score, f1_score
        from sklearn.model_selection import train_test_split
        import numpy as np
        if len(np.unique(y)) < 2:
            logger.warning(f"Single class for {model_type} - skipping")
            return None
        X_tr, X_te, _tr, _te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        scaler = StandardScaler()
        X_tr   = scaler.fit_transform(X_tr)
        X_te    = scaler.transform(X_te)
        clf = GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42)
        clf.fit(X_tr, y_tr)
        y_prob = clf.predict_proba(X_te)[:, 1]
        y_pred = clf.predict(X_te)
        auc      = float(roc_auc_score(y_te, y_prob))
        accuracy = float(accuracy_score(y_te, y_pred))
        f1_val   = float(f1_score(y_te, y_pred, zero_division=0))
        self._models[model_type]  = clf
        self._scalers[model_type] = scaler
        result = TrainingResult(
            model_type=model_type, auc_roc=auc, accuracy=accuracy, f1=f1_val,
            train_samples=len(X_tr), test_samples=len(X_te),
            trained_at=datetime.utcnow(), is_acceptable=(auc >= 0.55),
        )
        logger.info(f"Trained {model_type.value} | AUC{auc:.4f} acc{accuracy:.3f}")
        return result

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        clf    = self._models.get(ModelType.DIRECTION)
        scaler = self._scalers.get(ModelType.DIRECTION)
        if clf is None or scaler is None:
            return {"probability": 50.0, "confidence": 0.0, "model_available": False}
        try:
            import numpy as np
            feat_vec = np.array([list(features.values())], dtype=np.float32)
            feat_vec = scaler.transform(feat_vec)
            prob     = float(clf.predict_proba(feat_vec)[0, 1]) * 100.0
            result   = self._results.get(ModelType.DIRECTION)
            auc      = result.auc_roc if result else 0.0
            return {
                "probability":     round(prob, 2),
                "confidence":      round(min(auc * 100.0, 95.0), 2),
                "model_available": True,
                "model_auc":       round(auc, 4),
                "risk":            self._risk_level(prob, auc),
            }
        except Exception as exc:
            logger.error(f"Prediction error: {exc}")
            return {"probability": 50.0, "confidence": 0.0, "model_available": False}

    def save_models(self) -> None:
        for model_type, clf in self._models.items():
            try:
                path = self._model_dir / f"{model_type.value.lower()}_model.pkl"
                with open(path, "wb") as f: pickle.dump((clf, self._scalers.get(model_type)), f, protocol=5)
                logger.info(f"Model saved: {path}")
            except Exception as exc:
                logger.error(f"Failed to save {model_type}: {exc}")

    def load_models(self) -> bool:
        loaded = 0
        for model_type in ModelType:
            path = self._model_dir / f"{model_type.value.lower()}_model.pkl"
            if path.exists():
                try:
                    with open(path, "rb") as f: clf, scaler = pickle.load(f)
                    self._models[model_type]  = clf
                    self._scalers[model_type] = scaler
                    loaded += 1
                except Exception as exc:
                    logger.error(f"Failed to load {model_type}: {exc}")
        logger.info(f"Models loaded: {loaded}/{len(list(ModelType))}")
        return loaded > 0

    @staticmethod
    def _extract_features(trades):
        features, labels = [], []
        for trade in trades:
            try:
                ctx = trade.context if hasattr(trade, "context") else {}
                feat = [
                    float(ctx.get("order_block_quality", 0.0)),
                    float(ctx.get("fvg_quality", 0.0)),
                    float(ctx.get("bos_strength", 0.0)),
                    float(ctx.get("sweep_quality", 0.0)),
                    float(ctx.get("session_quality", 0.5)),
                    float(ctx.get("htf_score", 0.5)),
                    1.0 if ctx.get("in_kill_zone") else 0.0,
                    float(ctx.get("atr_normalized", 1.0)),
                    float(ctx.get("internal_liquidity", 0.0)),
                    float(ctx.get("external_liquidity", 0.0)),
                ]
                from .trade_memory import TradeOutcome
                label = 1 if getattr(trade, "outcome", None) == TradeOutcome.WIN else 0
                features.append(feat)
                labels.append(label)
            except Exception:
                continue
        return features, labels

    @staticmethod
    def _risk_level(prob: float, auc: float) -> str:
        if auc < 0.55: return "UNKNOWN"
        if prob >= 75: return "LOW"
        if prob >= 60: return "MEDIUM"
        if prob >= 45: return "HIGH"
        return "EXTREME"


class UnifiedMLEngine(MLEngine):
    """D2 Fix: Bridge between MLEngine v1 and TrainingPipeline v2."""

    def __init__(self, model_dir=None):
        super().__init__(model_dir=model_dir)
        self._pipeline = None
        self._use_v2   = False
        self._init_v2()

    def _init_v2(self):
        try:
            from ..self_learning.training_pipeline import TrainingPipeline
            self._pipeline = TrainingPipeline(model_dir=self._model_dir)
            self._use_v2   = True
            logger.info("UnifiedMLEngine: v2 TrainingPipeline available")
        except Exception as exc:
            logger.warning(f"UnifiedMLEngine: v2 unavailable ({exc}) - using v1")

    def train(self, memory) -> dict:
        if not self._use_v2 or self._pipeline is None:
            return super().train(memory)
        trades = memory.get_recent(1000) if hasattr(memory, "get_recent") else []
        if len(trades) < 30:
            return super().train(memory)
        try:
            import numpy as np
            features, labels = self._extract_features(trades)
            if len(features) < 20:
                return super().train(memory)
            X = np.array(features, dtype=np.float32)
            y = np.array(labels,   dtype=np.int32)
            v2_r = self._pipeline.train(X, y, symbol="UNIFIED")
            if v2_r and v2_r.is_acceptable:
                v1 = TrainingResult(
                    model_type=ModelType.DIRECTION,
                    auc_roc=v2_r.test_auc or v2_r.val_auc,
                    accuracy=v2_r.accuracy, f1=v2_r.f1_score,
                    train_samples=v2_r.train_samples,
                    test_samples=v2_r.test_samples,
                    trained_at=v2_r.trained_at, model_path=v2_r.model_path,
                    is_acceptable=True, feature_names=v2_r.feature_names,
                )
                self._results[ModelType.DIRECTION] = v1
                logger.info(f"UnifiedMLEngine v2 success | AUC={v1.auc_roc:.4f}")
                return {ModelType.DIRECTION: v1}
            logger.warning("v2 not acceptable - fallback to v1")
            return super().train(memory)
        except Exception as exc:
            logger.error(f"UnifiedMLEngine error: {exc} - fallback to v1")
            return super().train(memory)
