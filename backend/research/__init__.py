"""
================================================================================
Galaxy Vast AI Trading Platform
ماژول تحقیق و بررسی — Research Module

این پوشه شامل موتورهای بررسی و تحقیق است:
- موتور بک‌تست (Backtest Engine)
- موتور ریپلی بازار (Market Replay Engine)
- تحلیل Walk-Forward

نسخه: 3.0.0
برند: Galaxy Vast AI Trading Platform
================================================================================
"""

from .backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from .replay.engine import ReplayEngine, ReplayConfig, ReplayState
from .walk_forward.analyzer import WalkForwardAnalyzer, WalkForwardConfig

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "ReplayEngine",
    "ReplayConfig",
    "ReplayState",
    "WalkForwardAnalyzer",
    "WalkForwardConfig",
]
