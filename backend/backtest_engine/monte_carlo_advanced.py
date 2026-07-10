"""
backend/backtest_engine/monte_carlo_advanced.py
Monte Carlo simulation for advanced backtest analysis.
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MCResult:
    """Monte Carlo simulation result."""
    total_trades: int
    wins: int
    losses: int
    avg_win: float
    avg_loss: float
    max_dd: float
    confidence_95: Tuple[float, float]
    confidence_99: Tuple[float, float]


class MonteCarloEngine:
    """Advanced Monte Carlo simulation for backtest results."""

    def __init__(self, num_simulations: int = 10000):
        """
        Initialize Monte Carlo Engine.

        Args:
            num_simulations: Number of simulation runs
        """
        self.num_simulations = num_simulations
        logger.info("[mc] Initialized with %d simulations", num_simulations)

    def simulate(
        self,
        trades: List[dict],
        randomize_order: bool = True,
        confidence_level: float = 0.95
    ) -> MCResult:
        """
        Run Monte Carlo simulation on trade results.

        Args:
            trades: List of trades with profit/loss
            randomize_order: Randomize trade order
            confidence_level: Confidence interval (0.95 or 0.99)

        Returns:
            MCResult with statistics
        """
        if not trades or len(trades) < 2:
            logger.warning("[mc] Insufficient trades for simulation: %d", len(trades))
            return self._create_empty_result()

        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in trades if t['pnl'] <= 0]

        if not wins or not losses:
            logger.warning("[mc] No win or loss trades found")
            return self._create_empty_result()

        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)
        
        results = []
        for _ in range(self.num_simulations):
            sim_trades = np.random.choice(trades, len(trades), replace=True)
            sim_pnl = sum([t['pnl'] for t in sim_trades])
            results.append(sim_pnl)

        results = np.array(results)
        
        if confidence_level == 0.95:
            lower = np.percentile(results, 2.5)
            upper = np.percentile(results, 97.5)
        else:
            lower = np.percentile(results, 0.5)
            upper = np.percentile(results, 99.5)

        max_dd = self._calculate_max_dd(trades)

        logger.info(
            "[mc] Simulation complete: avg_win=%.2f, avg_loss=%.2f, max_dd=%.2f",
            avg_win, avg_loss, max_dd
        )

        return MCResult(
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_dd=max_dd,
            confidence_95=(lower, upper) if confidence_level == 0.95 else (0, 0),
            confidence_99=(lower, upper) if confidence_level == 0.99 else (0, 0)
        )

    @staticmethod
    def _calculate_max_dd(trades: List[dict]) -> float:
        """Calculate maximum drawdown from trades."""
        if not trades:
            return 0.0
        
        cumsum = np.cumsum([t['pnl'] for t in trades])
        running_max = np.maximum.accumulate(cumsum)
        dd = (cumsum - running_max) / (running_max + 1e-9)
        return float(np.min(dd))

    @staticmethod
    def _create_empty_result() -> MCResult:
        """Create empty result."""
        return MCResult(
            total_trades=0,
            wins=0,
            losses=0,
            avg_win=0.0,
            avg_loss=0.0,
            max_dd=0.0,
            confidence_95=(0, 0),
            confidence_99=(0, 0)
        )
