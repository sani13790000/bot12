"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
پکیج: AI Prediction Module

اجزاء:
  • FeatureExtractor  ← استخراج ویژگی از سیگنال‌های SMC
  • DatasetBuilder    ← ساخت dataset برای آموزش ML
  • XGBoostTrainer    ← آموزش و اعتبارسنجی مدل
  • PredictionService ← سرویس پیش‌بینی real-time
  • ModelManager      ← مدیریت چرخه عمر مدل‌ها
"""

from .feature_extractor import FeatureExtractor, SMCFeatures
from .dataset_builder import DatasetBuilder, TrainingDataset
from .xgboost_trainer import XGBoostTrainer, TrainingResult
from .prediction_service import PredictionService, PredictionResult, RiskLevel
from .model_manager import ModelManager, ModelMetadata

__all__ = [
    "FeatureExtractor",
    "SMCFeatures",
    "DatasetBuilder",
    "TrainingDataset",
    "XGBoostTrainer",
    "TrainingResult",
    "PredictionService",
    "PredictionResult",
    "RiskLevel",
    "ModelManager",
    "ModelMetadata",
]
