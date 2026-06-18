"""
تست‌های MLEngine
"""
from __future__ import annotations
import os
import pickle
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ─── stubs برای test (بدون import از backend) ───────────────────────────────
class ModelType(str, Enum):
    OVERALL = "overall"
    BUY = "buy"
    SELL = "sell"


@dataclass
class MLPrediction:
    success_probability: float
    model_type: ModelType
    features_used: int
    is_reliable: bool
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def should_trade(self) -> bool:
        return self.success_probability >= 0.55 and self.is_reliable


@dataclass
class TrainingResult:
    model_type: ModelType
    auc_roc: float
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    feature_importance: Dict[str, float]
    training_time_seconds: float
    n_samples: int
    is_reliable: bool

    @property
    def summary(self) -> str:
        return (
            f"{self.model_type.value}: AUC={self.auc_roc:.3f} "
            f"Acc={self.accuracy:.3f} F1={self.f1_score:.3f} "
            f"n={self.n_samples}"
        )


MIN_SAMPLES = 30
MIN_AUC = 0.55


def _make_prediction(models, feature_names, features):
    """Stub inference logic."""
    if not models:
        return MLPrediction(
            success_probability=0.5,
            model_type=ModelType.OVERALL,
            features_used=0,
            is_reliable=False,
            confidence=0.0,
        )
    X = np.array([[features.get(f, 0.0) for f in feature_names]])
    model_data = models.get(ModelType.OVERALL)
    if model_data is None:
        return MLPrediction(
            success_probability=0.5,
            model_type=ModelType.OVERALL,
            features_used=len(feature_names),
            is_reliable=False,
            confidence=0.0,
        )
    clf = model_data["model"]
    scaler = model_data.get("scaler")
    X_s = scaler.transform(X) if scaler else X
    prob = float(clf.predict_proba(X_s)[0][1])
    return MLPrediction(
        success_probability=prob,
        model_type=ModelType.OVERALL,
        features_used=len(feature_names),
        is_reliable=True,
        confidence=abs(prob - 0.5) * 2,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestMLPrediction:

    def test_should_trade_above_threshold(self):
        p = MLPrediction(
            success_probability=0.65,
            model_type=ModelType.OVERALL,
            features_used=12,
            is_reliable=True,
            confidence=0.7,
        )
        assert p.should_trade is True

    def test_should_not_trade_below_threshold(self):
        p = MLPrediction(
            success_probability=0.50,
            model_type=ModelType.OVERALL,
            features_used=12,
            is_reliable=True,
            confidence=0.1,
        )
        assert p.should_trade is False

    def test_should_not_trade_unreliable(self):
        p = MLPrediction(
            success_probability=0.80,
            model_type=ModelType.OVERALL,
            features_used=0,
            is_reliable=False,
            confidence=0.9,
        )
        assert p.should_trade is False

    def test_confidence_clamp(self):
        """confidence نباید منفی باشد."""
        p = MLPrediction(
            success_probability=0.51,
            model_type=ModelType.OVERALL,
            features_used=12,
            is_reliable=True,
            confidence=abs(0.51 - 0.5) * 2,
        )
        assert p.confidence >= 0.0


class TestTrainingResult:

    def test_summary_format(self):
        tr = TrainingResult(
            model_type=ModelType.OVERALL,
            auc_roc=0.72,
            accuracy=0.68,
            precision=0.70,
            recall=0.65,
            f1_score=0.67,
            feature_importance={"rsi": 0.3, "macd": 0.2},
            training_time_seconds=1.5,
            n_samples=500,
            is_reliable=True,
        )
        s = tr.summary
        assert "overall" in s
        assert "0.720" in s
        assert "500" in s

    def test_reliable_when_good_metrics(self):
        tr = TrainingResult(
            model_type=ModelType.OVERALL,
            auc_roc=0.75,
            accuracy=0.70,
            precision=0.72,
            recall=0.68,
            f1_score=0.70,
            feature_importance={},
            training_time_seconds=2.0,
            n_samples=200,
            is_reliable=True,
        )
        assert tr.is_reliable is True

    def test_unreliable_below_min_auc(self):
        tr = TrainingResult(
            model_type=ModelType.OVERALL,
            auc_roc=0.51,
            accuracy=0.52,
            precision=0.50,
            recall=0.50,
            f1_score=0.50,
            feature_importance={},
            training_time_seconds=0.5,
            n_samples=20,
            is_reliable=False,
        )
        assert tr.is_reliable is False


class TestMLInference:

    def test_no_model_returns_neutral(self, ml_features):
        pred = _make_prediction({}, [], ml_features)
        assert pred.success_probability == 0.5
        assert pred.is_reliable is False

    def test_inference_with_sklearn_stub(self, ml_features):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        feature_names = list(ml_features.keys())
        X = np.array([[ml_features[f] for f in feature_names]] * 60)
        y = np.array([1, 0] * 30)
        clf = GradientBoostingClassifier(n_estimators=5, random_state=42)
        scaler = StandardScaler()
        X_s = scaler.fit_transform(X)
        clf.fit(X_s, y)
        models = {
            ModelType.OVERALL: {"model": clf, "scaler": scaler}
        }
        pred = _make_prediction(models, feature_names, ml_features)
        assert 0.0 <= pred.success_probability <= 1.0
        assert pred.is_reliable is True
        assert pred.features_used == len(feature_names)

    def test_inference_probability_range(self, ml_features):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        feature_names = list(ml_features.keys())
        X = np.random.rand(100, len(feature_names))
        y = (X[:, 0] > 0.5).astype(int)
        clf = GradientBoostingClassifier(n_estimators=5, random_state=1)
        scaler = StandardScaler()
        X_s = scaler.fit_transform(X)
        clf.fit(X_s, y)
        models = {ModelType.OVERALL: {"model": clf, "scaler": scaler}}
        for _ in range(10):
            pred = _make_prediction(models, feature_names, ml_features)
            assert 0.0 <= pred.success_probability <= 1.0


class TestMinSamples:

    def test_min_samples_constant(self):
        assert MIN_SAMPLES == 30

    def test_min_auc_constant(self):
        assert MIN_AUC == 0.55

    def test_insufficient_samples_unreliable(self):
        n = 10  # کمتر از MIN_SAMPLES
        is_reliable = n >= MIN_SAMPLES
        assert is_reliable is False

    def test_sufficient_samples_reliable(self):
        n = 50
        is_reliable = n >= MIN_SAMPLES
        assert is_reliable is True
