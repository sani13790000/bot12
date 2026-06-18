"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Intelligence (هوش مصنوعی)

شامل:
  • TradeMemory     ← حافظه معاملاتی per-trade context
  • FailureAnalyzer ← تشخیص نقض قوانین vs زیان عادی
  • MLEngine        ← XGBoost + LightGBM + CatBoost
  • WeightAdjuster  ← تنظیم وزن اندیکاتورها
"""

from .trade_memory import TradeMemory, TradeContext, TradeOutcome
from .failure_analyzer import FailureAnalyzer, FailureReport, FailureType
from .ml_engine import MLEngine, MLPrediction, ModelType
from .weight_adjuster import WeightAdjuster, WeightUpdate

__all__ = [
    "TradeMemory", "TradeContext", "TradeOutcome",
    "FailureAnalyzer", "FailureReport", "FailureType",
    "MLEngine", "MLPrediction", "ModelType",
    "WeightAdjuster", "WeightUpdate",
]
