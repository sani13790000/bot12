"""Galaxy Vast AI Trading Platform
Parameter Optimization Engine

Grid Search + Bayesian-inspired optimization for strategy parameters.
Prevents overfitting via out-of-sample validation.

Phase-6 fix:
- Added ParameterRange as alias for ParameterGrid (walk_forward_advanced compatibility)
- Extended OptimizationConfig with WalkForward fields
- Added best_is_result / best_oos_result / best_fitness to OptimizationResult
"""
from __future__ import annotations
import asyncio
import itertools
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import math
import statistics


@dataclass
class ParameterGrid:
    """Defines the search space for optimization."""
    name: str
    min_value: float
    max_value: float
    step: float
    param_type: str = "float"  # float / int / bool

    def values(self) -> List[Any]:
        vals = []
        v = self.min_value
        while v <= self.max_value + 1e-9:
            if self.param_type == "int":
                vals.append(int(round(v)))
            elif self.param_type == "bool":
                vals.append(bool(int(round(v))))
            else:
                vals.append(round(v, 8))
            v += self.step
        return list(dict.fromkeys(vals))  # deduplicate


@dataclass
class ParameterRange:
    """Alias-style class: discrete list of values (used by walk_forward_advanced)."""
    name: str
    values_list: List[Any]

    def values(self) -> List[Any]:
        return list(self.values_list)

    # Allow construction as ParameterRange("name", [v1, v2, ...])
    def __init__(self, name: str, values_list: List[Any]):
        self.name = name
        self.values_list = values_list


@dataclass
class OptimizationConfig:
    # Core fields (original)
    parameter_grids: List[ParameterGrid] = field(default_factory=list)
    metric: str = "sharpe_ratio"            # objective metric to maximize
    method: str = "GRID"                    # GRID / RANDOM / WALK_FORWARD
    max_iterations: int = 200
    train_ratio: float = 0.70               # 70% train / 30% out-of-sample
    random_seed: int = 42
    min_trades: int = 30                    # discard runs with fewer trades
    penalty_overfitting: float = 0.5        # penalize train>>test gap
    n_jobs: int = 4                         # parallel workers

    # Walk-forward extra fields (Phase-6)
    symbols: List[str] = field(default_factory=lambda: ['XAUUSD'])
    parameter_ranges: List[ParameterRange] = field(default_factory=list)
    optimization_metric: str = "SHARPE"     # SHARPE / PROFIT_FACTOR / WIN_RATE
    initial_balance: float = 10_000.0
    is_start: Optional[datetime] = None
    is_end: Optional[datetime] = None
    oos_start: Optional[datetime] = None
    oos_end: Optional[datetime] = None


@dataclass
class IterationResult:
    params: Dict[str, Any]
    train_metric: float
    test_metric: float
    train_trades: int
    test_trades: int
    net_pnl: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    combined_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params,
            "train_metric": round(self.train_metric, 4),
            "test_metric":  round(self.test_metric, 4),
            "train_trades": self.train_trades,
            "test_trades":  self.test_trades,
            "net_pnl":      round(self.net_pnl, 2),
            "max_drawdown": round(self.max_drawdown, 4),
            "profit_factor":round(self.profit_factor, 4),
            "win_rate":     round(self.win_rate, 4),
            "combined_score": round(self.combined_score, 4),
        }


@dataclass
class OptimizationResult:
    config: OptimizationConfig
    best_params: Dict[str, Any]
    best_train_metric: float
    best_test_metric: float
    best_combined_score: float
    all_iterations: List[IterationResult]
    total_iterations: int
    is_robust: bool
    robustness_score: float           # 0-100
    overfit_warning: bool
    recommendation: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime   = field(default_factory=datetime.utcnow)

    # Phase-6: walk_forward_advanced compatibility
    best_fitness: float = 0.0
    best_is_result: Any = None   # MultiSymbolBacktestResult | None
    best_oos_result: Any = None  # MultiSymbolBacktestResult | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_params":          self.best_params,
            "best_train_metric":    round(self.best_train_metric, 4),
            "best_test_metric":     round(self.best_test_metric, 4),
            "best_combined_score":  round(self.best_combined_score, 4),
            "total_iterations":     self.total_iterations,
            "is_robust":            self.is_robust,
            "robustness_score":     round(self.robustness_score, 2),
            "overfit_warning":      self.overfit_warning,
            "recommendation":       self.recommendation,
            "top_10": [r.to_dict() for r in sorted(
                self.all_iterations, key=lambda x: x.combined_score, reverse=True
            )[:10]],
            "duration_seconds": round((self.end_time - self.start_time).total_seconds(), 2),
        }


class ParameterOptimizer:
    """
    Strategy parameter optimizer with overfitting detection.
    Supports grid search and random search with train/test split.
    Phase-6: also accepts ParameterRange (discrete list) in addition to ParameterGrid.
    """

    def __init__(self) -> None:
        self._results: List[IterationResult] = []

    async def optimize(
        self,
        config: OptimizationConfig,
        evaluator: Callable[[Dict[str, Any], bool], Tuple[float, int, float, float, float]],
        # evaluator(params, is_train) -> (metric, n_trades, net_pnl, max_dd, profit_factor)
    ) -> OptimizationResult:
        start = datetime.utcnow()
        self._results = []

        param_combinations = self._generate_combinations(config)

        # Limit iterations
        if len(param_combinations) > config.max_iterations:
            rng = random.Random(config.random_seed)
            param_combinations = rng.sample(param_combinations, config.max_iterations)

        # Evaluate all combinations
        semaphore = asyncio.Semaphore(config.n_jobs)
        tasks = [
            self._evaluate_one(params, config, evaluator, semaphore)
            for params in param_combinations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, IterationResult)]
        self._results = valid

        if not valid:
            return self._empty_result(config, start)

        # Find best
        best = max(valid, key=lambda r: r.combined_score)

        # Robustness analysis
        robustness = self._compute_robustness(valid)
        is_robust  = robustness >= 60.0
        overfit    = (best.train_metric - best.test_metric) > 0.5

        if overfit and not is_robust:
            recommendation = "OVERFITTED — do not deploy"
        elif is_robust:
            recommendation = "ROBUST — safe to deploy"
        else:
            recommendation = "ACCEPTABLE — monitor closely"

        end = datetime.utcnow()
        result = OptimizationResult(
            config=config,
            best_params=best.params,
            best_train_metric=best.train_metric,
            best_test_metric=best.test_metric,
            best_combined_score=best.combined_score,
            all_iterations=valid,
            total_iterations=len(valid),
            is_robust=is_robust,
            robustness_score=robustness,
            overfit_warning=overfit,
            recommendation=recommendation,
            start_time=start,
            end_time=end,
            best_fitness=best.combined_score,
        )
        return result

    # ── Internals ────────────────────────────────────────────────────────────
    async def _evaluate_one(
        self,
        params: Dict[str, Any],
        config: OptimizationConfig,
        evaluator: Callable,
        semaphore: asyncio.Semaphore,
    ) -> Optional[IterationResult]:
        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                train_metric, train_n, net_pnl, max_dd, pf = await loop.run_in_executor(
                    None, lambda: evaluator(params, True)
                )
                if train_n < config.min_trades:
                    return None
                test_metric, test_n, _, _, _ = await loop.run_in_executor(
                    None, lambda: evaluator(params, False)
                )
                # Combined score with overfitting penalty
                gap = max(0.0, train_metric - test_metric)
                combined = (train_metric + test_metric) / 2.0 - config.penalty_overfitting * gap
                return IterationResult(
                    params=params,
                    train_metric=train_metric,
                    test_metric=test_metric,
                    train_trades=train_n,
                    test_trades=test_n,
                    net_pnl=net_pnl,
                    max_drawdown=max_dd,
                    profit_factor=pf,
                    win_rate=0.0,
                    combined_score=combined,
                )
            except Exception:
                return None

    def _generate_combinations(self, config: OptimizationConfig) -> List[Dict[str, Any]]:
        """Support both ParameterGrid (range) and ParameterRange (discrete list)."""
        all_params: List[tuple] = []

        # ParameterRange (discrete list) — used by walk_forward_advanced
        for pr in config.parameter_ranges:
            all_params.append((pr.name, pr.values()))

        # ParameterGrid (min/max/step) — used by classic optimizer
        for pg in config.parameter_grids:
            all_params.append((pg.name, pg.values()))

        if not all_params:
            return [{}]

        names = [p[0] for p in all_params]
        value_lists = [p[1] for p in all_params]
        return [
            dict(zip(names, combo))
            for combo in itertools.product(*value_lists)
        ]

    def _calc_fitness(self, result: Any, metric: str) -> float:
        """Calculate fitness score from a MultiSymbolBacktestResult or similar."""
        if result is None:
            return 0.0
        metric_upper = metric.upper()
        if metric_upper == "SHARPE":
            return getattr(result, 'sharpe_ratio', 0.0)
        if metric_upper == "PROFIT_FACTOR":
            return getattr(result, 'profit_factor', 0.0)
        if metric_upper == "WIN_RATE":
            return getattr(result, 'win_rate', 0.0) / 100.0
        return getattr(result, 'net_profit_pct', 0.0)

    @staticmethod
    def _compute_robustness(results: List[IterationResult]) -> float:
        """Percentage of runs where test metric > 0 and train/test gap is within 50% of train metric."""
        if not results:
            return 0.0
        passing = sum(
            1 for r in results
            if r.test_metric > 0 and
               (r.train_metric == 0 or abs(r.train_metric - r.test_metric) / max(abs(r.train_metric), 1e-9) < 0.5)
        )
        return (passing / len(results)) * 100

    def _empty_result(self, config: OptimizationConfig, start: datetime) -> OptimizationResult:
        return OptimizationResult(
            config=config, best_params={}, best_train_metric=0,
            best_test_metric=0, best_combined_score=0, all_iterations=[],
            total_iterations=0, is_robust=False, robustness_score=0,
            overfit_warning=True, recommendation="INSUFFICIENT DATA",
            start_time=start, end_time=datetime.utcnow(),
            best_fitness=0.0,
        )
