"""Monte Carlo Simulator — equity path simulation with probability of ruin."""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class MonteCarloResult:
    n_simulations: int
    n_trades: int
    initial_balance: float
    # Distribution of final balances
    median_final_balance: float
    mean_final_balance: float
    percentile_5: float    # worst 5% scenario
    percentile_25: float
    percentile_75: float
    percentile_95: float   # best 5% scenario
    # Risk metrics
    probability_of_ruin: float     # % sims ending below ruin_threshold
    probability_of_profit: float   # % sims with profit
    expected_max_drawdown_pct: float
    # Paths
    sample_paths: List[List[float]]   # 10 sample equity paths
    all_final_balances: List[float]   # distribution histogram data
    ruin_threshold: float


class MonteCarloSimulator:
    """
    Monte Carlo simulation for trading strategy validation.

    Given a list of historical trade P&Ls, runs N simulations by
    randomly sampling (with replacement) to produce equity path distributions.
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        ruin_threshold_pct: float = 50.0,  # account considered "ruined" at 50% loss
        seed: Optional[int] = None,
    ):
        self._n = n_simulations
        self._ruin_pct = ruin_threshold_pct
        if seed is not None:
            random.seed(seed)

    def run(
        self,
        trade_pnls: List[float],
        initial_balance: float = 10_000.0,
    ) -> MonteCarloResult:

        if not trade_pnls:
            return self._empty(initial_balance)

        n_trades = len(trade_pnls)
        ruin_threshold = initial_balance * (1 - self._ruin_pct / 100)
        final_balances: List[float] = []
        max_drawdowns: List[float] = []
        sample_paths: List[List[float]] = []
        ruin_count = 0
        profit_count = 0

        for sim_idx in range(self._n):
            balance = initial_balance
            peak = initial_balance
            max_dd = 0.0
            path = [initial_balance]

            # Random sample WITH replacement
            sampled = random.choices(trade_pnls, k=n_trades)

            for pnl in sampled:
                balance += pnl
                path.append(balance)
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
                if balance <= ruin_threshold:
                    ruin_count += 1
                    break

            final_balances.append(balance)
            max_drawdowns.append(max_dd)
            if balance > initial_balance:
                profit_count += 1

            if sim_idx < 10:  # save first 10 paths as samples
                sample_paths.append(path)

        final_balances.sort()
        n = len(final_balances)

        def percentile(sorted_list: List[float], pct: float) -> float:
            idx = int(len(sorted_list) * pct / 100)
            return sorted_list[min(idx, len(sorted_list) - 1)]

        return MonteCarloResult(
            n_simulations=self._n,
            n_trades=n_trades,
            initial_balance=initial_balance,
            median_final_balance=round(percentile(final_balances, 50), 2),
            mean_final_balance=round(sum(final_balances) / n, 2),
            percentile_5=round(percentile(final_balances, 5), 2),
            percentile_25=round(percentile(final_balances, 25), 2),
            percentile_75=round(percentile(final_balances, 75), 2),
            percentile_95=round(percentile(final_balances, 95), 2),
            probability_of_ruin=round(ruin_count / self._n * 100, 2),
            probability_of_profit=round(profit_count / self._n * 100, 2),
            expected_max_drawdown_pct=round(sum(max_drawdowns) / len(max_drawdowns), 2),
            sample_paths=sample_paths,
            all_final_balances=final_balances,
            ruin_threshold=ruin_threshold,
        )

    def _empty(self, initial_balance: float) -> MonteCarloResult:
        return MonteCarloResult(
            n_simulations=0, n_trades=0, initial_balance=initial_balance,
            median_final_balance=initial_balance, mean_final_balance=initial_balance,
            percentile_5=initial_balance, percentile_25=initial_balance,
            percentile_75=initial_balance, percentile_95=initial_balance,
            probability_of_ruin=0.0, probability_of_profit=0.0,
            expected_max_drawdown_pct=0.0, sample_paths=[], all_final_balances=[],
            ruin_threshold=initial_balance * 0.5,
        )
