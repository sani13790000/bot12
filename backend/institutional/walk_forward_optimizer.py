"""Walk-Forward Optimizer — Train / Validation / Test splits with parameter grid search."""

from __future__ import annotations
import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class WFOConfig:
    n_windows: int = 5              # number of IS/OOS windows
    is_pct: float = 0.70            # in-sample % of each window
    val_pct: float = 0.15           # validation %
    oos_pct: float = 0.15           # out-of-sample (test) %
    optimization_metric: str = "sharpe_ratio"   # metric to maximize
    min_trades_per_window: int = 10
    parameter_grid: Dict[str, List[Any]] = field(default_factory=dict)
    # e.g. {"sl_pips": [10, 15, 20], "tp_multiplier": [1.5, 2.0, 2.5]}


@dataclass
class WindowResult:
    window_idx: int
    is_start: int       # candle index
    is_end: int
    val_start: int
    val_end: int
    oos_start: int
    oos_end: int
    best_params: Dict[str, Any]
    is_metric: float
    val_metric: float
    oos_metric: float
    is_trades: int
    oos_trades: int
    is_equity_curve: List[Tuple[float, float]]
    oos_equity_curve: List[Tuple[float, float]]
    robustness_ratio: float  # oos_metric / is_metric


@dataclass
class WFOResult:
    config: WFOConfig
    windows: List[WindowResult]
    combined_oos_trades: List[Dict]
    combined_oos_equity: List[Tuple[float, float]]
    avg_is_metric: float
    avg_val_metric: float
    avg_oos_metric: float
    avg_robustness_ratio: float
    best_params_overall: Dict[str, Any]   # most frequent best params
    is_robust: bool                        # avg robustness_ratio > 0.5
    total_oos_trades: int
    oos_win_rate: float
    oos_profit_factor: float


class WalkForwardOptimizer:
    """
    Walk-Forward Optimizer.

    For each window:
      1. Grid-search parameters on IS (train) period
      2. Validate on VAL period
      3. Apply best params to OOS (test) period
    
    Produces combined OOS equity curve — the only unbiased performance estimate.
    """

    def __init__(self, config: WFOConfig):
        self.config = config

    def run(
        self,
        candles: List[Dict],
        backtest_fn: Callable[[List[Dict], Dict], Dict],
        # backtest_fn(candles, params) -> {trades:[{net_profit,...}], equity_curve:[...], sharpe_ratio:float, ...}
    ) -> WFOResult:

        windows = self._split_windows(candles)
        window_results: List[WindowResult] = []
        all_oos_trades: List[Dict] = []
        combined_equity: List[Tuple[float, float]] = []
        running_equity = 10_000.0

        for idx, (is_s, is_e, val_s, val_e, oos_s, oos_e) in enumerate(windows):
            is_candles = candles[is_s:is_e]
            val_candles = candles[val_s:val_e]
            oos_candles = candles[oos_s:oos_e]

            # Grid search on IS
            best_params, is_metric = self._grid_search(is_candles, backtest_fn)

            # Validate
            val_result = backtest_fn(val_candles, best_params)
            val_metric = val_result.get(self.config.optimization_metric, 0.0)

            # OOS test
            oos_result = backtest_fn(oos_candles, best_params)
            oos_metric = oos_result.get(self.config.optimization_metric, 0.0)
            oos_trades = oos_result.get("trades", [])

            # Adjust OOS equity curve to be continuous
            oos_eq = oos_result.get("equity_curve", [])
            if oos_eq:
                start_eq = oos_eq[0][1]
                adjusted = [(ts, running_equity + (eq - start_eq)) for ts, eq in oos_eq]
                combined_equity.extend(adjusted)
                if adjusted:
                    running_equity = adjusted[-1][1]

            robustness = oos_metric / is_metric if is_metric > 0 else 0

            window_results.append(WindowResult(
                window_idx=idx,
                is_start=is_s, is_end=is_e,
                val_start=val_s, val_end=val_e,
                oos_start=oos_s, oos_end=oos_e,
                best_params=best_params,
                is_metric=round(is_metric, 4),
                val_metric=round(val_metric, 4),
                oos_metric=round(oos_metric, 4),
                is_trades=len(backtest_fn(is_candles, best_params).get("trades", [])),
                oos_trades=len(oos_trades),
                is_equity_curve=backtest_fn(is_candles, best_params).get("equity_curve", []),
                oos_equity_curve=oos_result.get("equity_curve", []),
                robustness_ratio=round(robustness, 4),
            ))
            all_oos_trades.extend(oos_trades)

        avg_is = sum(w.is_metric for w in window_results) / len(window_results)
        avg_val = sum(w.val_metric for w in window_results) / len(window_results)
        avg_oos = sum(w.oos_metric for w in window_results) / len(window_results)
        avg_rob = sum(w.robustness_ratio for w in window_results) / len(window_results)

        oos_winners = [t for t in all_oos_trades if t.get("net_profit", 0) > 0]
        oos_losers = [t for t in all_oos_trades if t.get("net_profit", 0) <= 0]
        oos_gross_win = sum(t.get("net_profit", 0) for t in oos_winners)
        oos_gross_loss = abs(sum(t.get("net_profit", 0) for t in oos_losers))

        best_params_overall = self._most_common_params(window_results)

        return WFOResult(
            config=self.config,
            windows=window_results,
            combined_oos_trades=all_oos_trades,
            combined_oos_equity=combined_equity,
            avg_is_metric=round(avg_is, 4),
            avg_val_metric=round(avg_val, 4),
            avg_oos_metric=round(avg_oos, 4),
            avg_robustness_ratio=round(avg_rob, 4),
            best_params_overall=best_params_overall,
            is_robust=avg_rob >= 0.5,
            total_oos_trades=len(all_oos_trades),
            oos_win_rate=len(oos_winners) / len(all_oos_trades) * 100 if all_oos_trades else 0,
            oos_profit_factor=oos_gross_win / oos_gross_loss if oos_gross_loss > 0 else 0,
        )

    def _split_windows(self, candles: List[Dict]) -> List[Tuple[int, int, int, int, int, int]]:
        """Split candles into N windows, each with IS/VAL/OOS portions."""
        n = len(candles)
        window_size = n // self.config.n_windows
        windows = []
        for i in range(self.config.n_windows):
            start = i * window_size
            end = start + window_size if i < self.config.n_windows - 1 else n
            size = end - start
            is_end = start + int(size * self.config.is_pct)
            val_end = is_end + int(size * self.config.val_pct)
            oos_end = end
            if is_end < start + 10 or val_end < is_end + 5 or oos_end < val_end + 5:
                continue
            windows.append((start, is_end, is_end, val_end, val_end, oos_end))
        return windows

    def _grid_search(
        self, candles: List[Dict], backtest_fn: Callable
    ) -> Tuple[Dict, float]:
        """Exhaustive grid search over parameter_grid."""
        if not self.config.parameter_grid:
            result = backtest_fn(candles, {})
            return {}, result.get(self.config.optimization_metric, 0.0)

        keys = list(self.config.parameter_grid.keys())
        values = list(self.config.parameter_grid.values())
        best_metric = float("-inf")
        best_params: Dict[str, Any] = {}

        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            try:
                result = backtest_fn(candles, params)
                metric = result.get(self.config.optimization_metric, float("-inf"))
                trades = result.get("trades", [])
                if len(trades) < self.config.min_trades_per_window:
                    continue
                if metric > best_metric:
                    best_metric = metric
                    best_params = params
            except Exception:
                continue

        return best_params, best_metric

    @staticmethod
    def _most_common_params(windows: List[WindowResult]) -> Dict[str, Any]:
        """Return the most frequently selected parameters across windows."""
        if not windows:
            return {}
        param_votes: Dict[str, Dict[Any, int]] = {}
        for w in windows:
            for k, v in w.best_params.items():
                if k not in param_votes:
                    param_votes[k] = {}
                param_votes[k][v] = param_votes[k].get(v, 0) + 1
        return {k: max(votes, key=votes.get) for k, votes in param_votes.items()}
