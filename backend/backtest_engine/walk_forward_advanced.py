"""
Galaxy Vast AI Trading Platform
WalkForwardAdvanced — Rolling window IS/OOS analysis with parameter optimization

Features:
  - Rolling window with configurable IS/OOS split
  - Per-window parameter optimization
  - Stability score across windows
  - Overfitting detection
  - Anchored vs rolling modes
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .multi_symbol_engine import MultiSymbolBacktestEngine, MultiSymbolConfig, MultiSymbolResult
from .parameter_optimizer import ParameterOptimizer, OptimizationConfig, ParameterRange
from .data_provider import CandleDataProvider, Timeframe


@dataclass
class WalkForwardWindow:
    """One IS/OOS window."""
    window_id:    int
    is_start:     datetime
    is_end:       datetime
    oos_start:    datetime
    oos_end:      datetime
    best_params:  Dict[str, Any]          = field(default_factory=dict)
    is_result:    Optional[MultiSymbolResult] = None
    oos_result:   Optional[MultiSymbolResult] = None
    passed:       bool  = False
    fitness_is:   float = 0.0
    fitness_oos:  float = 0.0
    efficiency:   float = 0.0  # OOS / IS fitness ratio

    def to_dict(self) -> dict:
        def _s(r):
            if r is None: return None
            return {"sharpe": r.sharpe_ratio, "pf": r.profit_factor,
                    "wr": round(r.win_rate*100,1), "net_pct": r.net_profit_pct,
                    "trades": r.total_trades, "mdd": r.max_drawdown_pct}
        return {
            "window_id":  self.window_id,
            "is_period":  f"{self.is_start.date()} → {self.is_end.date()}",
            "oos_period": f"{self.oos_start.date()} → {self.oos_end.date()}",
            "best_params":self.best_params,
            "passed":     self.passed,
            "fitness_is": round(self.fitness_is, 3),
            "fitness_oos":round(self.fitness_oos, 3),
            "efficiency": round(self.efficiency * 100, 1),
            "is_metrics": _s(self.is_result),
            "oos_metrics":_s(self.oos_result),
        }


@dataclass
class WalkForwardAdvancedConfig:
    symbols:          List[str]
    data_start:       datetime
    data_end:         datetime
    is_months:        int   = 6     # In-sample period months
    oos_months:       int   = 2     # Out-of-sample period months
    step_months:      int   = 1     # Slide step months
    mode:             str   = "ROLLING"   # ROLLING | ANCHORED
    min_oos_trades:   int   = 10
    pass_threshold:   float = 0.4   # OOS/IS efficiency threshold
    initial_balance:  float = 10_000.0
    parameter_ranges: Optional[List[ParameterRange]] = None
    optimization_metric: str = "SHARPE"


@dataclass
class WalkForwardAdvancedResult:
    config:           WalkForwardAdvancedConfig
    windows:          List[WalkForwardWindow] = field(default_factory=list)
    total_windows:    int   = 0
    passed_windows:   int   = 0
    pass_rate:        float = 0.0
    avg_efficiency:   float = 0.0
    consistency_score:float = 0.0
    recommendation:   str   = ""
    oos_combined_pnl: float = 0.0
    oos_combined_wr:  float = 0.0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_windows":    self.total_windows,
                "passed_windows":   self.passed_windows,
                "pass_rate":        round(self.pass_rate * 100, 1),
                "avg_efficiency":   round(self.avg_efficiency * 100, 1),
                "consistency_score":round(self.consistency_score, 1),
                "recommendation":   self.recommendation,
                "oos_combined_pnl": round(self.oos_combined_pnl, 2),
                "oos_combined_wr":  round(self.oos_combined_wr * 100, 1),
            },
            "windows": [w.to_dict() for w in self.windows],
        }


class WalkForwardAdvancedEngine:
    """
    Advanced Walk-Forward Analysis Engine with per-window optimization.

    Workflow per window:
      1. Optimize parameters on IS period
      2. Apply best params to OOS period
      3. Check pass/fail criteria
      4. Aggregate results
    """

    def __init__(self, data_provider: Optional[CandleDataProvider] = None) -> None:
        self._provider  = data_provider or CandleDataProvider()
        self._optimizer = ParameterOptimizer(self._provider)
        self._engine    = MultiSymbolBacktestEngine(self._provider)

    async def run(self, config: WalkForwardAdvancedConfig) -> WalkForwardAdvancedResult:
        result = WalkForwardAdvancedResult(config=config)
        windows = self._build_windows(config)

        # Run each window sequentially (optimization is already parallel internally)
        for wf_window in windows:
            await self._process_window(wf_window, config)
            result.windows.append(wf_window)

        self._aggregate(result)
        return result

    # ── Window builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_windows(config: WalkForwardAdvancedConfig) -> List[WalkForwardWindow]:
        windows: List[WalkForwardWindow] = []
        window_id = 1
        oos_start = config.data_start + timedelta(days=config.is_months * 30)

        while True:
            is_start = (config.data_start if config.mode == "ANCHORED"
                        else oos_start - timedelta(days=config.is_months * 30))
            is_end   = oos_start - timedelta(days=1)
            oos_end  = oos_start + timedelta(days=config.oos_months * 30 - 1)

            if oos_end > config.data_end:
                break

            windows.append(WalkForwardWindow(
                window_id=window_id,
                is_start=is_start, is_end=is_end,
                oos_start=oos_start, oos_end=oos_end,
            ))
            oos_start += timedelta(days=config.step_months * 30)
            window_id += 1

        return windows

    # ── Window processor ─────────────────────────────────────────────────────

    async def _process_window(
        self, wf_window: WalkForwardWindow, config: WalkForwardAdvancedConfig
    ) -> None:
        # Default parameter ranges if not provided
        param_ranges = config.parameter_ranges or [
            ParameterRange("rr_ratio",          [1.5, 2.0, 2.5, 3.0]),
            ParameterRange("min_confidence",    [60.0, 65.0, 70.0, 75.0]),
            ParameterRange("atr_multiplier",    [1.0, 1.5, 2.0]),
            ParameterRange("risk_per_trade_pct",[0.5, 1.0, 1.5]),
        ]

        opt_config = OptimizationConfig(
            symbols=config.symbols,
            parameter_ranges=param_ranges,
            method="GRID",
            optimization_metric=config.optimization_metric,
            initial_balance=config.initial_balance,
            is_start=wf_window.is_start,
            is_end=wf_window.is_end,
            oos_start=wf_window.oos_start,
            oos_end=wf_window.oos_end,
        )

        opt_result = await self._optimizer.optimize(opt_config)
        wf_window.best_params = opt_result.best_params
        wf_window.is_result   = opt_result.best_is_result
        wf_window.oos_result  = opt_result.best_oos_result

        # Score
        if wf_window.is_result:
            wf_window.fitness_is = opt_result.best_fitness
        if wf_window.oos_result:
            wf_window.fitness_oos = self._optimizer._calc_fitness(
                wf_window.oos_result, config.optimization_metric
            )

        # Efficiency ratio and pass/fail
        if wf_window.fitness_is > 0:
            wf_window.efficiency = wf_window.fitness_oos / wf_window.fitness_is
        oos_trades = wf_window.oos_result.total_trades if wf_window.oos_result else 0
        wf_window.passed = (
            wf_window.efficiency >= config.pass_threshold
            and oos_trades >= config.min_oos_trades
            and (wf_window.oos_result.net_profit_pct > 0 if wf_window.oos_result else False)
        )

    # ── Aggregation ───────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate(result: WalkForwardAdvancedResult) -> None:
        result.total_windows  = len(result.windows)
        result.passed_windows = sum(1 for w in result.windows if w.passed)
        result.pass_rate      = result.passed_windows / result.total_windows if result.total_windows else 0

        efficiencies = [w.efficiency for w in result.windows if w.efficiency > 0]
        result.avg_efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0

        # Consistency: std of OOS fitness
        oos_fitnesses = [w.fitness_oos for w in result.windows]
        if oos_fitnesses:
            avg = sum(oos_fitnesses) / len(oos_fitnesses)
            std = (sum((f - avg)**2 for f in oos_fitnesses) / len(oos_fitnesses)) ** 0.5
            cv  = std / abs(avg) if avg != 0 else 1.0
            result.consistency_score = max(0, 100 * (1 - cv))
        else:
            result.consistency_score = 0

        # OOS combined
        oos_results = [w.oos_result for w in result.windows if w.oos_result]
        if oos_results:
            total_pnl = sum(r.net_profit_pct for r in oos_results)
            result.oos_combined_pnl = total_pnl
            wins  = sum(r.winning_trades for r in oos_results)
            total = sum(r.total_trades for r in oos_results)
            result.oos_combined_wr = wins / total if total > 0 else 0

        # Recommendation
        if result.pass_rate >= 0.7 and result.avg_efficiency >= 0.5:
            result.recommendation = "ROBUST — Deploy with confidence"
        elif result.pass_rate >= 0.5:
            result.recommendation = "ACCEPTABLE — Monitor closely in live trading"
        elif result.pass_rate >= 0.3:
            result.recommendation = "MARGINAL — Reduce position size, needs improvement"
        else:
            result.recommendation = "OVERFITTED — Do NOT deploy, strategy needs redesign"
