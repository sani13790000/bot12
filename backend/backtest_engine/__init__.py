"""Backtest engine package.

Public API
----------
MultiSymbolBacktestEngine  - core engine
DataProvider               - candle loader / registry
WalkForwardAnalyzer        - WFO from walk_forward_advanced
MonteCarloSimulator        - MC from monte_carlo_advanced
"""
from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
from backend.backtest_engine.data_provider import DataProvider
from backend.backtest_engine.walk_forward_advanced import WalkForwardAnalyzer
from backend.backtest_engine.monte_carlo_advanced import MonteCarloSimulator

__all__ = [
    "MultiSymbolBacktestEngine",
    "DataProvider",
    "WalkForwardAnalyzer",
    "MonteCarloSimulator",
]
