"""Galaxy Vast AI Trading Platform — Monte Carlo Simulation Engine.

- Reshuffle trade returns to generate equity paths
- Confidence intervals
- Probability of ruin
- Max drawdown distribution
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from backend.research.backtest.engine import BacktestTrade, SharedBacktestMetrics


@dataclass
class MonteCarloResult:
    simulations: int
    final_equity_median: float
    final_equity_5pct: float
    final_equity_95pct: float
    max_dd_median_pct: float
    max_dd_95pct_pct: float
    probability_of_ruin: float
    probability_of_profit: float
    sharpe_median: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulations": self.simulations,
            "final_equity_median": round(self.final_equity_median, 2),
            "final_equity_5pct": round(self.final_equity_5pct, 2),
            "final_equity_95pct": round(self.final_equity_95pct, 2),
            "max_dd_median_pct": round(self.max_dd_median_pct, 4),
            "max_dd_95pct_pct": round(self.max_dd_95pct_pct, 4),
            "probability_of_ruin": round(self.probability_of_ruin, 4),
            "probability_of_profit": round(self.probability_of_profit, 4),
            "sharpe_median": round(self.sharpe_median, 4),
        }


class MonteCarloEngine:
    """Monte Carlo simulation for trading strategy robustness."""

    def __init__(self, initial_balance: float = 100_000.0):
        self.initial_balance = initial_balance

    def run(
        self,
        trades: List[BacktestTrade],
        simulations: int = 1000,
        ruin_threshold_pct: float = 50.0,
    ) -> MonteCarloResult:
        if not trades or simulations <= 0:
            return MonteCarloResult(
                simulations=simulations,
                final_equity_median=self.initial_balance,
                final_equity_5pct=self.initial_balance,
                final_equity_95pct=self.initial_balance,
                max_dd_median_pct=0.0,
                max_dd_95pct_pct=0.0,
                probability_of_ruin=0.0,
                probability_of_profit=0.0,
                sharpe_median=0.0,
            )

        returns = [t.pnl_usd for t in trades]
        n = len(returns)
        final_equities = []
        max_dds = []
        sharpes = []
        ruin_count = 0
        profit_count = 0
        ruin_level = self.initial_balance * (1 - ruin_threshold_pct / 100.0)

        rng = np.random.default_rng(seed=42)
        for _ in range(simulations):
            shuffled = rng.choice(returns, size=n, replace=True)
            equity = [self.initial_balance]
            for r in shuffled:
                equity.append(equity[-1] + r)
            final = equity[-1]
            final_equities.append(final)
            if final <= ruin_level:
                ruin_count += 1
            if final > self.initial_balance:
                profit_count += 1

            pct_dd, _ = SharedBacktestMetrics.max_drawdown(equity)
            max_dds.append(pct_dd)

            rets = [r / self.initial_balance for r in shuffled]
            sharpes.append(SharedBacktestMetrics.sharpe_ratio(rets))

        final_equities = np.array(final_equities)
        max_dds = np.array(max_dds)
        sharpes = np.array([s for s in sharpes if math.isfinite(s)] or [0.0])

        return MonteCarloResult(
            simulations=simulations,
            final_equity_median=float(np.median(final_equities)),
            final_equity_5pct=float(np.percentile(final_equities, 5)),
            final_equity_95pct=float(np.percentile(final_equities, 95)),
            max_dd_median_pct=float(np.median(max_dds)),
            max_dd_95pct_pct=float(np.percentile(max_dds, 95)),
            probability_of_ruin=ruin_count / simulations,
            probability_of_profit=profit_count / simulations,
            sharpe_median=float(np.median(sharpes)),
        )
