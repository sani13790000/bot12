"""
Galaxy Vast AI Trading Platform
MonteCarloAdvanced — Institutional Monte Carlo simulation engine

Features:
  - Trade shuffling + bootstrap resampling
  - Configurable simulations (100–10,000)
  - VaR / CVaR at multiple confidence levels
  - Ruin probability (equity < threshold)
  - Percentile equity curves (p5, p25, p50, p75, p95)
  - Position sizing sensitivity analysis
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .multi_symbol_engine import BacktestTrade


@dataclass
class MonteCarloAdvancedConfig:
    n_simulations:       int   = 1000
    initial_balance:     float = 10_000.0
    ruin_threshold_pct:  float = 20.0    # ruin if drawdown > this %
    confidence_levels:   List[float] = field(default_factory=lambda: [0.90, 0.95, 0.99])
    seed:                Optional[int] = None
    resampling_method:   str = "SHUFFLE"  # SHUFFLE | BOOTSTRAP


@dataclass
class PercentileCurve:
    """Equity curves at key percentiles."""
    p5:  List[float] = field(default_factory=list)
    p25: List[float] = field(default_factory=list)
    p50: List[float] = field(default_factory=list)
    p75: List[float] = field(default_factory=list)
    p95: List[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"p5": self.p5, "p25": self.p25, "p50": self.p50,
                "p75": self.p75, "p95": self.p95}


@dataclass
class MonteCarloAdvancedResult:
    config:                 MonteCarloAdvancedConfig
    n_simulations_run:      int   = 0

    # Core statistics
    probability_profit:     float = 0.0   # % of sims that ended profitable
    probability_ruin:       float = 0.0   # % of sims that hit ruin threshold
    expected_final_balance: float = 0.0
    median_final_balance:   float = 0.0

    # Drawdown statistics
    expected_max_drawdown:  float = 0.0
    worst_max_drawdown:     float = 0.0
    median_max_drawdown:    float = 0.0

    # VaR / CVaR (as % of initial balance)
    var_by_level:           Dict[str, float] = field(default_factory=dict)
    cvar_by_level:          Dict[str, float] = field(default_factory=dict)

    # Percentile equity curves
    percentile_curves:      PercentileCurve = field(default_factory=PercentileCurve)

    # Distribution
    final_balance_p5:       float = 0.0
    final_balance_p25:      float = 0.0
    final_balance_p75:      float = 0.0
    final_balance_p95:      float = 0.0
    std_final_balance:      float = 0.0

    # Sensitivity
    optimal_risk_pct:       float = 0.0   # risk % that maximizes median return
    kelly_fraction:         float = 0.0

    def to_dict(self) -> dict:
        return {
            "simulations_run":       self.n_simulations_run,
            "probability_profit_pct":round(self.probability_profit * 100, 1),
            "probability_ruin_pct":  round(self.probability_ruin * 100, 2),
            "expected_final_balance":round(self.expected_final_balance, 2),
            "median_final_balance":  round(self.median_final_balance, 2),
            "std_final_balance":     round(self.std_final_balance, 2),
            "distribution": {
                "p5":  round(self.final_balance_p5, 2),
                "p25": round(self.final_balance_p25, 2),
                "p50": round(self.median_final_balance, 2),
                "p75": round(self.final_balance_p75, 2),
                "p95": round(self.final_balance_p95, 2),
            },
            "drawdown": {
                "expected_max_pct": round(self.expected_max_drawdown * 100, 2),
                "worst_max_pct":    round(self.worst_max_drawdown * 100, 2),
                "median_max_pct":   round(self.median_max_drawdown * 100, 2),
            },
            "var":  {k: round(v * 100, 2) for k, v in self.var_by_level.items()},
            "cvar": {k: round(v * 100, 2) for k, v in self.cvar_by_level.items()},
            "percentile_curves": self.percentile_curves.to_dict(),
            "kelly_fraction":    round(self.kelly_fraction, 4),
            "optimal_risk_pct":  round(self.optimal_risk_pct, 2),
        }


class MonteCarloAdvancedSimulator:
    """
    Institutional Monte Carlo Simulator.

    Takes a list of closed BacktestTrades and simulates thousands of
    random orderings to compute risk statistics.
    """

    def __init__(self) -> None:
        pass

    def run(
        self,
        trades: List[BacktestTrade],
        config: Optional[MonteCarloAdvancedConfig] = None,
    ) -> MonteCarloAdvancedResult:
        """Run full Monte Carlo simulation."""
        cfg    = config or MonteCarloAdvancedConfig()
        result = MonteCarloAdvancedResult(config=cfg)

        if not trades:
            return result

        if cfg.seed is not None:
            random.seed(cfg.seed)

        pnl_list = [t.pnl for t in trades]
        initial  = cfg.initial_balance
        ruin_threshold = initial * (1 - cfg.ruin_threshold_pct / 100)

        # Run simulations
        all_final_balances: List[float] = []
        all_max_drawdowns:  List[float] = []
        all_equity_paths:   List[List[float]] = []
        n_ruin  = 0

        for sim_idx in range(cfg.n_simulations):
            if cfg.resampling_method == "BOOTSTRAP":
                sampled = random.choices(pnl_list, k=len(pnl_list))
            else:
                sampled = pnl_list.copy()
                random.shuffle(sampled)

            equity    = initial
            peak      = initial
            max_dd    = 0.0
            ruined    = False
            path      = [initial]

            for pnl in sampled:
                equity += pnl
                peak    = max(peak, equity)
                dd      = (peak - equity) / peak if peak > 0 else 0
                max_dd  = max(max_dd, dd)
                path.append(round(equity, 2))
                if equity <= ruin_threshold:
                    ruined = True

            all_final_balances.append(equity)
            all_max_drawdowns.append(max_dd)
            if sim_idx < 200:  # Keep first 200 paths for curves
                all_equity_paths.append(path)
            if ruined:
                n_ruin += 1

        all_final_balances.sort()
        all_max_drawdowns.sort()

        n = cfg.n_simulations
        result.n_simulations_run      = n
        result.probability_profit     = sum(1 for b in all_final_balances if b > initial) / n
        result.probability_ruin       = n_ruin / n
        result.expected_final_balance = sum(all_final_balances) / n
        result.median_final_balance   = statistics.median(all_final_balances)
        result.std_final_balance      = statistics.stdev(all_final_balances) if n > 1 else 0

        result.final_balance_p5  = all_final_balances[int(n * 0.05)]
        result.final_balance_p25 = all_final_balances[int(n * 0.25)]
        result.final_balance_p75 = all_final_balances[int(n * 0.75)]
        result.final_balance_p95 = all_final_balances[int(n * 0.95)]

        result.expected_max_drawdown = sum(all_max_drawdowns) / n
        result.worst_max_drawdown    = max(all_max_drawdowns)
        result.median_max_drawdown   = statistics.median(all_max_drawdowns)

        # VaR / CVaR
        pnl_outcomes = [b - initial for b in all_final_balances]
        for cl in cfg.confidence_levels:
            key    = f"{int(cl*100)}pct"
            idx    = int((1 - cl) * n)
            var    = -pnl_outcomes[idx] / initial
            cvar   = -sum(pnl_outcomes[:idx+1]) / (idx + 1) / initial if idx >= 0 else var
            result.var_by_level[key]  = var
            result.cvar_by_level[key] = cvar

        # Percentile curves
        if all_equity_paths:
            max_len = max(len(p) for p in all_equity_paths)
            padded  = [p + [p[-1]] * (max_len - len(p)) for p in all_equity_paths]
            result.percentile_curves = PercentileCurve(
                p5  = self._percentile_curve(padded, 5),
                p25 = self._percentile_curve(padded, 25),
                p50 = self._percentile_curve(padded, 50),
                p75 = self._percentile_curve(padded, 75),
                p95 = self._percentile_curve(padded, 95),
            )

        # Kelly fraction
        wins  = [p for p in pnl_list if p > 0]
        losses= [abs(p) for p in pnl_list if p < 0]
        if wins and losses:
            wr    = len(wins) / len(pnl_list)
            avg_w = sum(wins) / len(wins)
            avg_l = sum(losses) / len(losses)
            b     = avg_w / avg_l
            result.kelly_fraction    = max(0, wr - (1 - wr) / b) if b > 0 else 0
            result.optimal_risk_pct  = round(result.kelly_fraction * 0.5 * 100, 2)  # Half-Kelly

        return result

    @staticmethod
    def _percentile_curve(paths: List[List[float]], pct: int) -> List[float]:
        """Compute percentile at each time step across all paths."""
        n_steps = len(paths[0]) if paths else 0
        result  = []
        for step in range(n_steps):
            vals = sorted(p[step] for p in paths)
            idx  = int(len(vals) * pct / 100)
            result.append(round(vals[min(idx, len(vals)-1)], 2))
        return result
