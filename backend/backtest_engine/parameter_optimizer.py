"""
Galaxy Vast AI Trading Platform
ParameterOptimizer — Grid Search + Genetic Algorithm parameter optimization

Features:
  - Grid search over parameter space
  - Genetic algorithm optimization
  - Multi-objective fitness (Sharpe × PF × WinRate)
  - Overfitting detection via IS/OOS comparison
  - Full audit trail of all tested combinations
"""

from __future__ import annotations

import asyncio
import itertools
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .multi_symbol_engine import MultiSymbolBacktestEngine, MultiSymbolConfig, MultiSymbolResult
from .data_provider import CandleDataProvider, Timeframe


@dataclass
class ParameterRange:
    """Definition of one optimizable parameter."""
    name:    str
    values:  List[Any]   # discrete values to test
    current: Any = None  # current/default value

    def __post_init__(self):
        if self.current is None and self.values:
            self.current = self.values[0]


@dataclass
class OptimizationConfig:
    """Full optimization configuration."""
    symbols:            List[str]
    parameter_ranges:   List[ParameterRange]
    method:             str       = "GRID"          # GRID | GENETIC
    optimization_metric: str     = "SHARPE"         # SHARPE | PROFIT_FACTOR | NET_PROFIT | CALMAR
    initial_balance:    float     = 10_000.0
    is_start:           Optional[datetime] = None   # In-sample start
    is_end:             Optional[datetime] = None   # In-sample end
    oos_start:          Optional[datetime] = None   # Out-of-sample start
    oos_end:            Optional[datetime] = None   # Out-of-sample end
    max_iterations:     int       = 500             # For GENETIC
    population_size:    int       = 30              # For GENETIC
    elite_fraction:     float     = 0.2
    mutation_rate:      float     = 0.15
    overfitting_ratio:  float     = 0.5             # OOS/IS metric ratio threshold


@dataclass
class TestedCombination:
    """Result of one tested parameter combination."""
    params:           Dict[str, Any]
    is_result:        Optional[MultiSymbolResult] = None
    oos_result:       Optional[MultiSymbolResult] = None
    fitness:          float = 0.0
    overfitting_flag: bool  = False

    def to_dict(self) -> dict:
        return {
            "params":          self.params,
            "fitness":         round(self.fitness, 4),
            "overfitting":     self.overfitting_flag,
            "is_metrics":      self._result_summary(self.is_result),
            "oos_metrics":     self._result_summary(self.oos_result),
        }

    @staticmethod
    def _result_summary(r: Optional[MultiSymbolResult]) -> Optional[dict]:
        if r is None:
            return None
        return {
            "net_profit_pct":  r.net_profit_pct,
            "sharpe_ratio":    r.sharpe_ratio,
            "profit_factor":   r.profit_factor,
            "win_rate":        round(r.win_rate * 100, 1),
            "max_drawdown":    r.max_drawdown_pct,
            "total_trades":    r.total_trades,
        }


@dataclass
class OptimizationResult:
    """Full optimization output."""
    config:           OptimizationConfig
    best_params:      Dict[str, Any]        = field(default_factory=dict)
    best_fitness:     float                 = 0.0
    best_is_result:   Optional[MultiSymbolResult] = None
    best_oos_result:  Optional[MultiSymbolResult] = None
    all_combinations: List[TestedCombination] = field(default_factory=list)
    total_tested:     int                   = 0
    is_overfit:       bool                  = False
    optimization_time_sec: float            = 0.0

    def to_dict(self) -> dict:
        return {
            "best_params":     self.best_params,
            "best_fitness":    round(self.best_fitness, 4),
            "is_overfit":      self.is_overfit,
            "total_tested":    self.total_tested,
            "optimization_time_sec": round(self.optimization_time_sec, 1),
            "best_is_metrics": TestedCombination._result_summary(self.best_is_result),
            "best_oos_metrics":TestedCombination._result_summary(self.best_oos_result),
            "top10": [c.to_dict() for c in sorted(
                self.all_combinations, key=lambda x: x.fitness, reverse=True
            )[:10]],
        }


class ParameterOptimizer:
    """
    Institutional Parameter Optimizer.

    Supports:
      - Grid Search (exhaustive)
      - Genetic Algorithm (heuristic for large spaces)
      - IS/OOS overfitting detection
      - Multi-objective fitness scoring
    """

    def __init__(self, data_provider: Optional[CandleDataProvider] = None) -> None:
        self._provider = data_provider or CandleDataProvider()
        self._engine   = MultiSymbolBacktestEngine(self._provider)

    # ── Public API ────────────────────────────────────────────────────────────

    async def optimize(self, opt_config: OptimizationConfig) -> OptimizationResult:
        """Run full optimization and return best parameters."""
        start_time = datetime.utcnow()
        result = OptimizationResult(config=opt_config)

        if opt_config.method == "GENETIC":
            combinations = await self._genetic_search(opt_config)
        else:
            combinations = await self._grid_search(opt_config)

        result.all_combinations = combinations
        result.total_tested     = len(combinations)

        if combinations:
            best = max(combinations, key=lambda c: c.fitness)
            result.best_params    = best.params
            result.best_fitness   = best.fitness
            result.best_is_result = best.is_result
            result.best_oos_result = best.oos_result
            result.is_overfit     = best.overfitting_flag

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        result.optimization_time_sec = elapsed
        return result

    # ── Grid Search ───────────────────────────────────────────────────────────

    async def _grid_search(
        self, opt_config: OptimizationConfig
    ) -> List[TestedCombination]:
        """Exhaustive grid search over all parameter combinations."""
        param_names  = [pr.name   for pr in opt_config.parameter_ranges]
        param_values = [pr.values for pr in opt_config.parameter_ranges]

        all_combos = list(itertools.product(*param_values))
        # Cap at 200 for performance
        if len(all_combos) > 200:
            random.shuffle(all_combos)
            all_combos = all_combos[:200]

        # Run in batches of 10 concurrently
        results: List[TestedCombination] = []
        batch_size = 10
        for i in range(0, len(all_combos), batch_size):
            batch = all_combos[i:i + batch_size]
            tasks = [
                self._evaluate_combination(
                    dict(zip(param_names, combo)), opt_config
                )
                for combo in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_results:
                if isinstance(r, TestedCombination):
                    results.append(r)

        return results

    # ── Genetic Algorithm ─────────────────────────────────────────────────────

    async def _genetic_search(
        self, opt_config: OptimizationConfig
    ) -> List[TestedCombination]:
        """Genetic algorithm for large parameter spaces."""
        param_names  = [pr.name   for pr in opt_config.parameter_ranges]
        param_values = [pr.values for pr in opt_config.parameter_ranges]

        def random_individual() -> Dict[str, Any]:
            return {name: random.choice(vals) for name, vals in zip(param_names, param_values)}

        def mutate(ind: Dict[str, Any]) -> Dict[str, Any]:
            ind = ind.copy()
            for name, vals in zip(param_names, param_values):
                if random.random() < opt_config.mutation_rate:
                    ind[name] = random.choice(vals)
            return ind

        def crossover(p1: Dict[str, Any], p2: Dict[str, Any]) -> Dict[str, Any]:
            child = {}
            for name in param_names:
                child[name] = p1[name] if random.random() < 0.5 else p2[name]
            return child

        population = [random_individual() for _ in range(opt_config.population_size)]
        all_tested: List[TestedCombination] = []
        seen: set = set()

        for generation in range(opt_config.max_iterations // opt_config.population_size):
            # Evaluate population
            tasks = []
            for ind in population:
                key = str(sorted(ind.items()))
                if key not in seen:
                    seen.add(key)
                    tasks.append(self._evaluate_combination(ind, opt_config))

            if tasks:
                evaluated = await asyncio.gather(*tasks, return_exceptions=True)
                gen_results = [r for r in evaluated if isinstance(r, TestedCombination)]
                all_tested.extend(gen_results)

            if not all_tested:
                break

            # Select elite
            all_tested.sort(key=lambda c: c.fitness, reverse=True)
            elite_n = max(2, int(opt_config.population_size * opt_config.elite_fraction))
            elite   = [c.params for c in all_tested[:elite_n]]

            # Next generation: elite + crossover + mutation
            next_gen = list(elite)
            while len(next_gen) < opt_config.population_size:
                if len(elite) >= 2:
                    p1, p2 = random.sample(elite, 2)
                    child = crossover(p1, p2)
                else:
                    child = random_individual()
                next_gen.append(mutate(child))
            population = next_gen

        return all_tested

    # ── Combination evaluator ─────────────────────────────────────────────────

    async def _evaluate_combination(
        self,
        params: Dict[str, Any],
        opt_config: OptimizationConfig,
    ) -> TestedCombination:
        """Run IS + OOS backtest for one parameter set."""
        combo = TestedCombination(params=params)

        # Build IS config
        is_config = self._build_config(params, opt_config, is_phase=True)
        try:
            combo.is_result = await self._engine.run(is_config)
        except Exception:
            combo.fitness = -999.0
            return combo

        combo.fitness = self._calc_fitness(combo.is_result, opt_config.optimization_metric)

        # Run OOS if configured
        if opt_config.oos_start and opt_config.oos_end:
            oos_config = self._build_config(params, opt_config, is_phase=False)
            try:
                combo.oos_result = await self._engine.run(oos_config)
                oos_fitness = self._calc_fitness(combo.oos_result, opt_config.optimization_metric)
                ratio = oos_fitness / combo.fitness if combo.fitness > 0 else 0
                combo.overfitting_flag = ratio < opt_config.overfitting_ratio
            except Exception:
                combo.overfitting_flag = True

        return combo

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_config(
        self,
        params: Dict[str, Any],
        opt_config: OptimizationConfig,
        is_phase: bool,
    ) -> MultiSymbolConfig:
        start = opt_config.is_start if is_phase else opt_config.oos_start
        end   = opt_config.is_end   if is_phase else opt_config.oos_end
        return MultiSymbolConfig(
            symbols=opt_config.symbols,
            initial_balance=opt_config.initial_balance,
            start_date=start,
            end_date=end,
            risk_per_trade_pct=params.get("risk_per_trade_pct", 1.0),
            rr_ratio=params.get("rr_ratio", 2.0),
            min_confidence=params.get("min_confidence", 65.0),
            atr_multiplier=params.get("atr_multiplier", 1.5),
        )

    @staticmethod
    def _calc_fitness(result: MultiSymbolResult, metric: str) -> float:
        """Multi-objective fitness score."""
        if result.total_trades < 5:
            return -999.0
        if metric == "SHARPE":
            return result.sharpe_ratio
        if metric == "PROFIT_FACTOR":
            return min(result.profit_factor, 10.0)  # cap infinite PF
        if metric == "NET_PROFIT":
            return result.net_profit_pct
        if metric == "CALMAR":
            return result.calmar_ratio
        # Default: composite
        pf_score = min(result.profit_factor, 5.0) / 5.0
        wr_score = result.win_rate
        sh_score = min(max(result.sharpe_ratio, -1), 3) / 3.0
        return (pf_score * 0.4 + wr_score * 0.3 + sh_score * 0.3) * 100
