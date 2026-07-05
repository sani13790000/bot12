"""
Phase G — ML Pipeline Integration Tests
Covers: ModelManager, PredictionService, FeaturePipeline, ContextEnricher ML layer,
        XGBoostTrainer.train_latest(), RetrainingService
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# ────────────────────────────────────────────────────────────────
class TestFeaturePipeline:
    """Tests for 38-feature pipeline consistency."""

    def test_feature_names_length(self):
        from backend.ai_prediction.feature_pipeline import get_feature_names
        names = get_feature_names()
        assert len(names) == 38, f"Expected 38, got {len(names)}"

    def test_feature_names_stable(self):
        from backend.ai_prediction.feature_pipeline import get_feature_names
        assert get_feature_names() == get_feature_names()

    def test_schema_hash_stable(self):
        from backend.ai_prediction.feature_pipeline import feature_schema_hash
        assert feature_schema_hash() == feature_schema_hash()
        assert len(feature_schema_hash()) == 8

    def test_build_feature_vector_length(self):
        from backend.ai_prediction.feature_pipeline import build_feature_vector
        ctx = {"symbol": "EURUSD", "direction": "BUY", "confidence": 0.7}
        feats = build_feature_vector(ctx)
        assert len(feats) == 38

    def test_build_features_from_context_shape(self):
        from backend.ai_prediction.feature_pipeline import build_features_from_context
        ctx = {"symbol": "XAUUSD", "direction": "SELL", "smc_confidence": 0.8}
        X = build_features_from_context(ctx)
        assert X.shape == (1, 38)
        assert X.dtype == np.float32

    def test_nan_safety(self):
        from backend.ai_prediction.feature_pipeline import build_feature_vector
        ctx = {"rsi_14": float("nan"), "spread_ratio": float("inf"), "direction": "BUY"}
        feats = build_feature_vector(ctx)
        assert all(np.isfinite(f) for f in feats), "NaN/inf in feature vector"

    def test_direction_encoding(self):
        from backend.ai_prediction.feature_pipeline import build_feature_vector
        buy  = build_feature_vector({"direction": "BUY"})
        sell = build_feature_vector({"direction": "SELL"})
        neut = build_feature_vector({"direction": "NEUTRAL"})
        # direction_aligned is index 16
        assert buy[16] == 1.0
        assert sell[16] == -1.0
        assert neut[16] == 0.0


# ────────────────────────────────────────────────────────────────
class TestModelManager:
    """Tests for versioned model storage."""

    def test_load_best_model_no_models(self, tmp_path):
        from backend.ai_prediction.model_manager import ModelManager
        mm = ModelManager(model_dir=str(tmp_path))
        assert mm.load_best_model() is None

    def test_save_and_load_model(self, tmp_path):
        from backend.ai_prediction.model_manager import ModelManager, ModelMetadata
        from datetime import datetime, timezone
        mm = ModelManager(model_dir=str(tmp_path))
        fake_model = MagicMock()
        meta = ModelMetadata(
            symbol="EURUSD",
            trained_at=datetime.now(timezone.utc).isoformat(),
            n_samples=500, accuracy=0.62, precision=0.60,
            recall=0.58, f1=0.59, auc_roc=0.68,
        )
        path = mm.save_model(fake_model, meta)
        assert path.endswith(".pkl")
        loaded = mm.load_best_model("EURUSD")
        assert loaded is not None

    def test_manifest_best_auc_wins(self, tmp_path):
        from backend.ai_prediction.model_manager import ModelManager, ModelMetadata
        from datetime import datetime, timezone
        mm = ModelManager(model_dir=str(tmp_path))
        fake_model = MagicMock()
        for auc in [0.60, 0.75, 0.65]:  # 0.75 should win
            meta = ModelMetadata(
                symbol="EURUSD",
                trained_at=datetime.now(timezone.utc).isoformat(),
                n_samples=100, accuracy=auc, precision=auc,
                recall=auc, f1=auc, auc_roc=auc,
            )
            mm.save_model(fake_model, meta)
        models = mm.list_models()
        assert len(models) == 1
        assert models[0].auc_roc == 0.75

    def test_get_best_metadata(self, tmp_path):
        from backend.ai_prediction.model_manager import ModelManager, ModelMetadata
        from datetime import datetime, timezone
        mm = ModelManager(model_dir=str(tmp_path))
        meta = ModelMetadata(
            symbol="XAUUSD",
            trained_at=datetime.now(timezone.utc).isoformat(),
            n_samples=200, accuracy=0.70, precision=0.68,
            recall=0.72, f1=0.70, auc_roc=0.74,
        )
        mm.save_model(MagicMock(), meta)
        loaded_meta = mm.get_best_metadata("XAUUSD")
        assert loaded_meta is not None
        assert loaded_meta.auc_roc == 0.74
        assert loaded_meta.n_samples == 200


# ────────────────────────────────────────────────────────────────
class TestPredictionService:
    """Tests for PredictionService."""

    @pytest.mark.asyncio
    async def test_predict_no_model_returns_fallback(self):
        from backend.ai_prediction.prediction_service import PredictionService
        svc = PredictionService()
        svc._manager = MagicMock()
        svc._manager.load_best_model.return_value = None
        result = await svc.predict({"symbol": "EURUSD", "direction": "BUY"})
        assert result.is_fallback is True
        assert result.is_tradeable is False

    @pytest.mark.asyncio
    async def test_predict_with_mock_model(self):
        from backend.ai_prediction.prediction_service import PredictionService
        svc = PredictionService(min_probability=60, min_confidence=50)
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.25, 0.75]])
        svc._manager = MagicMock()
        svc._manager.load_best_model.return_value = mock_model
        svc._manager.get_best_metadata.return_value = MagicMock(auc_roc=0.72, n_samples=1000)
        result = await svc.predict({"symbol": "EURUSD", "direction": "BUY", "confidence": 0.8})
        assert result.probability == 75
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_predict_below_threshold(self):
        from backend.ai_prediction.prediction_service import PredictionService
        svc = PredictionService(min_probability=60)
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.65, 0.35]])
        svc._manager = MagicMock()
        svc._manager.load_best_model.return_value = mock_model
        svc._manager.get_best_metadata.return_value = None
        result = await svc.predict({"symbol": "EURUSD", "direction": "SELL"})
        assert result.probability == 35
        assert result.is_tradeable is False

    def test_lazy_lock_init(self):
        from backend.ai_prediction.prediction_service import PredictionService
        svc = PredictionService()
        # Lock should be None until get_lock() is called inside running loop
        assert svc._lock is None


# ────────────────────────────────────────────────────────────────
class TestRetrainingService:
    """Tests for RetrainingService."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        from backend.self_learning.retraining_service import RetrainingService
        svc = RetrainingService(interval_hours=0.001)
        mock_trainer = AsyncMock()
        mock_trainer.train_latest = AsyncMock(return_value=MagicMock(
            accuracy=0.65, f1=0.62, n_samples=100, model_path="/tmp/m.pkl"
        ))
        svc.set_trainer(mock_trainer)
        await svc.start()
        assert svc._running is True
        await svc.stop()
        assert svc._running is False

    def test_set_trainer(self):
        from backend.self_learning.retraining_service import RetrainingService
        svc = RetrainingService()
        mock = MagicMock()
        svc.set_trainer(mock)
        assert svc._trainer is mock

    def test_stats_initial(self):
        from backend.self_learning.retraining_service import RetrainingService
        svc = RetrainingService()
        stats = svc.stats()
        assert stats["running"] is False
        assert stats["last_run"] is None
        assert stats["last_accuracy"] is None

    @pytest.mark.asyncio
    async def test_retrain_imports_correct_path(self):
        """BUG-G9: Ensures correct import path is used."""
        from backend.self_learning.retraining_service import RetrainingService
        svc = RetrainingService()
        # Should not raise ImportError with correct path
        with patch(
            "backend.ai_prediction.xgboost_trainer.XGBoostTrainer"
        ) as mock_cls:
            mock_trainer = AsyncMock()
            mock_trainer.train_latest = AsyncMock(return_value=MagicMock(
                accuracy=0.65, f1=0.62, n_samples=100, model_path=None
            ))
            mock_cls.return_value = mock_trainer
            svc._trainer = None
            await svc._retrain()
