"""Tests for backtest engine routes."""
from __future__ import annotations

import pytest


def test_backtest_request_schema() -> None:
    """BacktestRequest should validate correctly."""
    from backend.api.routes.backtest_engine import BacktestRequest
    req = BacktestRequest(
        symbol="XAUUSD",
        timeframe="H1",
        start_date="2024-01-01",
        end_date="2024-12-31",
        initial_balance=10_000.0,
        risk_pct=1.0,
        strategy="smc_pa",
    )
    assert req.symbol == "XAUUSD"
    assert req.initial_balance == 10_000.0


def test_walk_forward_request_schema() -> None:
    from backend.api.routes.backtest_engine import WalkForwardRequest
    req = WalkForwardRequest(n_folds=5, is_ratio=0.7)
    assert req.n_folds == 5
    assert req.is_ratio == 0.7


def test_monte_carlo_request_schema() -> None:
    from backend.api.routes.backtest_engine import MonteCarloRequest
    req = MonteCarloRequest(n_simulations=500, ruin_threshold=0.5)
    assert req.n_simulations == 500


def test_job_timeout_configured() -> None:
    from backend.api.routes.backtest_engine import JOB_TIMEOUT_SECONDS, MAX_JOBS_STORED
    assert JOB_TIMEOUT_SECONDS == 300
    assert MAX_JOBS_STORED == 500


def test_executor_not_none() -> None:
    from backend.api.routes.backtest_engine import _executor
    assert _executor is not None
