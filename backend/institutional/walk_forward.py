"""Galaxy Vast AI Trading Platform — Walk-Forward Optimization.

Features:
- Train / Validation / Test periods
- Automatic parameter optimization
- Multi-symbol support
- Per-window metrics and aggregated recommendation
"""
from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.research.backtest.engine import CandleData
from backend.institutional.tick_backtest import TickBacktestConfig, TickBacktestEngine


@dataclass
class WFOWindow:
    train_start: datetime
    train_end: datetime
    val_start: datetime
    val_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: Dict[str, Any] = field(default_factory=dict)
    is_metrics: Dict[str, Any] = field(default_factory=dict)
    oos_metrics: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "val_start": self.val_start.isoformat(),
            "val_end": self.val_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "best_params": self.best_params,
            "is_metrics": self.is_metrics,
            "oos_metrics": self.oos_metrics,
            "passed": self.passed,
        }


@dataclass
class WalkForwardConfig:
    symbols: List[str] = field(default_factory=lambda: ["XAUUSD"])
    timeframe: str = "M15"
    train_days: int = 90
    validation_days: int = 30
    test_days: int = 30
    step_days: int = 30
    parameter_grid: Dict[str, List[Any]] = field(default_factory=dict)
    optimization_metric: str = "sharpe_ratio"
    min_oos_trades: int = 5
    pass_threshold_efficiency: float = 0.5


class WalkForwardOptimizer:
    """Walk-forward analysis with train/val/test split and grid search."""

    DEFAULT_GRID = {
        "risk_per_trade_pct": [0.5, 1.0, 1.5],
        "slippage_pips": [0.2, 0.5],
        "max_trades_per_day": [5, 10],
    }

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self.config = config or WalkForwardConfig()
        if not self.config.parameter_grid:
            self.config.parameter_grid = self.DEFAULT_GRID

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> List[WFOWindow]:
        windows = []
        current = start_date
        train_d = timedelta(days=self.config.train_days)
        val_d = timedelta(days=self.config.validation_days)
        test_d = timedelta(days=self.config.test_days)
        step_d = timedelta(days=self.config.step_days)

        while current + train_d + val_d + test_d <= end_date:
            train_start = current
            train_end = current + train_d
            val_start = train_end
            val_end = val_start + val_d
            test_start = val_end
            test_end = test_start + test_d
            windows.append(WFOWindow(
                train_start=train_start,
                train_end=train_end,
                val_start=val_start,
                val_end=val_end,
                test_start=test_start,
                test_end=test_end,
            ))
            current += step_d
        return windows

    def optimize(
        self,
        candles_by_symbol: Dict[str, List[CandleData]],
        signal_generator: Callable[..., Optional[Dict[str, Any]]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not candles_by_symbol:
            raise ValueError("No candle data provided")

        all_timestamps = [c.timestamp for clist in candles_by_symbol.values() for c in clist]
        start = start_date or min(all_timestamps)
        end = end_date or max(all_timestamps)
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)

        windows = self.generate_windows(start, end)
        if not windows:
            raise ValueError("Date range too short for walk-forward windows")

        for w in windows:
            best_params, best_score = self._optimize_window(
                candles_by_symbol, signal_generator, w.train_start, w.train_end
            )
            w.best_params = best_params

            is_result = self._run_backtest(
                candles_by_symbol, signal_generator, best_params,
                w.train_start, w.train_end,
            )
            w.is_metrics = is_result.get("metrics", {})

            oos_result = self._run_backtest(
                candles_by_symbol, signal_generator, best_params,
                w.test_start, w.test_end,
            )
            w.oos_metrics = oos_result.get("metrics", {})

            efficiency = self._efficiency(w.is_metrics, w.oos_metrics)
            oos_trades = oos_result.get("total_trades", 0)
            oos_profit = oos_result.get("total_return_pct", 0.0)
            w.passed = (
                efficiency >= self.config.pass_threshold_efficiency
                and oos_trades >= self.config.min_oos_trades
                and oos_profit > 0
            )

        return self._aggregate(windows)

    def _optimize_window(
        self,
        candles_by_symbol: Dict[str, List[CandleData]],
        signal_generator: Callable[..., Optional[Dict[str, Any]]],
        start: datetime,
        end: datetime,
    ) -> Tuple[Dict[str, Any], float]:
        keys = list(self.config.parameter_grid.keys())
        values = [self.config.parameter_grid[k] for k in keys]
        best_score = -float("inf")
        best_params = {}

        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            result = self._run_backtest(candles_by_symbol, signal_generator, params, start, end)
            metrics = result.get("metrics", {})
            score = metrics.get(self.config.optimization_metric, 0.0)
            if not isinstance(score, (int, float)) or not math.isfinite(score):
                score = 0.0
            if score > best_score:
                best_score = score
                best_params = params.copy()

        return best_params, best_score

    def _run_backtest(
        self,
        candles_by_symbol: Dict[str, List[CandleData]],
        signal_generator: Callable[..., Optional[Dict[str, Any]]],
        params: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> Dict[str, Any]:
        filtered = {
            sym: [c for c in clist if start <= datetime.fromisoformat(c.timestamp) <= end]
            for sym, clist in candles_by_symbol.items()
        }
        config = TickBacktestConfig(
            symbols=self.config.symbols,
            timeframes=[self.config.timeframe],
            risk_per_trade_pct=params.get("risk_per_trade_pct", 1.0),
            slippage_pips=params.get("slippage_pips", 0.3),
            max_trades_per_day=params.get("max_trades_per_day", 10),
        )
        engine = TickBacktestEngine(config)
        engine.set_signal_generator(signal_generator)
        return engine.run(filtered, timeframe=self.config.timeframe)

    @staticmethod
    def _efficiency(is_metrics: Dict[str, Any], oos_metrics: Dict[str, Any]) -> float:
        is_sharpe = is_metrics.get("sharpe_ratio", 0.0) or 0.0
        oos_sharpe = oos_metrics.get("sharpe_ratio", 0.0) or 0.0
        if is_sharpe <= 0:
            return 0.0
        return max(0.0, min(1.0, oos_sharpe / is_sharpe))

    def _aggregate(self, windows: List[WFOWindow]) -> Dict[str, Any]:
        passed = [w for w in windows if w.passed]
        efficiencies = [self._efficiency(w.is_metrics, w.oos_metrics) for w in windows]
        oos_returns = [w.oos_metrics.get("total_return_pct", 0.0) for w in windows]
        oos_sharpes = [w.oos_metrics.get("sharpe_ratio", 0.0) for w in windows]

        if not efficiencies:
            recommendation = "NO_DATA"
        elif len(passed) / len(windows) >= 0.7 and statistics.mean(efficiencies) >= 0.5:
            recommendation = "ROBUST — Deploy with confidence"
        elif len(passed) / len(windows) >= 0.5:
            recommendation = "ACCEPTABLE — Monitor closely in live trading"
        elif len(passed) / len(windows) >= 0.3:
            recommendation = "MARGINAL — Reduce position size, needs improvement"
        else:
            recommendation = "OVERFITTED — Do NOT deploy, strategy needs redesign"

        return {
            "total_windows": len(windows),
            "passed_windows": len(passed),
            "pass_rate": round(len(passed) / len(windows), 4) if windows else 0.0,
            "avg_efficiency": round(statistics.mean(efficiencies), 4) if efficiencies else 0.0,
            "avg_oos_return_pct": round(statistics.mean(oos_returns), 4) if oos_returns else 0.0,
            "avg_oos_sharpe": round(statistics.mean(oos_sharpes), 4) if oos_sharpes else 0.0,
            "recommendation": recommendation,
            "windows": [w.to_dict() for w in windows],
        }
