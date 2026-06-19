"""Smoke tests for institutional modules."""
from __future__ import annotations

import importlib
import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "backend.institutional.market_replay",
        "backend.institutional.tick_backtest",
        "backend.institutional.performance_metrics",
        "backend.institutional.walk_forward_optimizer",
        "backend.institutional.ai_explainability",
        "backend.institutional.rl_agent",
        "backend.institutional.portfolio_manager",
        "backend.institutional.correlation_engine",
        "backend.institutional.monte_carlo",
        "backend.institutional.risk_engine",
        "backend.institutional.data_store",
    ],
)
def test_institutional_module_importable(module_path: str) -> None:
    """Every institutional module must be importable."""
    mod = importlib.import_module(module_path)
    assert mod is not None


def test_rl_environment_init() -> None:
    """RLEnvironment must initialise with XAUUSD symbol."""
    from backend.institutional.rl_agent import RLEnvironment

    candles = [
        {"open": 2000.0, "high": 2010.0, "low": 1990.0, "close": 2005.0, "volume": 100.0}
        for _ in range(60)
    ]
    env = RLEnvironment(candles=candles, symbol="XAUUSD")
    assert env._pip_size == 0.1


def test_rl_environment_eurusd() -> None:
    """RLEnvironment pip_size must be correct for EURUSD."""
    from backend.institutional.rl_agent import RLEnvironment

    candles = [
        {"open": 1.08, "high": 1.085, "low": 1.075, "close": 1.082, "volume": 50.0}
        for _ in range(60)
    ]
    env = RLEnvironment(candles=candles, symbol="EURUSD")
    assert env._pip_size == 0.0001
