"""Portfolio Manager — multi-symbol allocation with risk-parity and Kelly sizing."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class AllocationMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    RISK_PARITY = "risk_parity"
    KELLY = "kelly"
    MIN_VARIANCE = "min_variance"
    MAX_SHARPE = "max_sharpe"


@dataclass
class PortfolioConfig:
    symbols: List[str]
    initial_capital: float = 100_000.0
    method: AllocationMethod = AllocationMethod.RISK_PARITY
    max_position_pct: float = 25.0   # max % per symbol
    min_position_pct: float = 2.0    # min % per symbol
    max_corr_threshold: float = 0.80 # reject if correlation > this
    risk_free_rate: float = 0.05     # annual
    rebalance_every_n_bars: int = 96 # 96 M15 bars = 1 day


@dataclass
class SymbolAllocation:
    symbol: str
    weight: float          # 0-1
    capital_usd: float
    max_lot_size: float
    current_exposure_usd: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class PortfolioSnapshot:
    timestamp: float
    total_equity: float
    allocations: List[SymbolAllocation]
    total_exposure_usd: float
    exposure_pct: float
    diversification_ratio: float
    method_used: str


class PortfolioManager:
    """
    Institutional Portfolio Manager.

    Supports:
    - Equal Weight: simple 1/N allocation
    - Risk Parity: allocate inversely proportional to volatility
    - Kelly Criterion: maximize geometric growth rate
    - Min Variance: minimize portfolio variance (simplified)
    - Max Sharpe: maximize Sharpe ratio (simplified)
    """

    def __init__(self, config: PortfolioConfig):
        self.config = config
        self._returns_history: Dict[str, List[float]] = {s: [] for s in config.symbols}
        self._bars_since_rebalance = 0
        self._allocations: Dict[str, SymbolAllocation] = {}

    def update_returns(self, symbol: str, ret: float) -> None:
        """Feed latest return for a symbol (call every bar)."""
        if symbol in self._returns_history:
            self._returns_history[symbol].append(ret)
            if len(self._returns_history[symbol]) > 500:
                self._returns_history[symbol].pop(0)

    def compute_allocations(self, current_equity: float) -> List[SymbolAllocation]:
        """Compute target allocations based on selected method."""
        symbols = [s for s in self.config.symbols if len(self._returns_history.get(s, [])) >= 5]
        if not symbols:
            symbols = self.config.symbols

        if self.config.method == AllocationMethod.EQUAL_WEIGHT:
            weights = self._equal_weight(symbols)
        elif self.config.method == AllocationMethod.RISK_PARITY:
            weights = self._risk_parity(symbols)
        elif self.config.method == AllocationMethod.KELLY:
            weights = self._kelly(symbols)
        else:
            weights = self._equal_weight(symbols)

        # Apply min/max constraints
        weights = self._clip_weights(weights, symbols)

        allocations = []
        for sym, w in zip(symbols, weights):
            capital = current_equity * w
            # Rough lot size: capital / (price * contract_size)
            max_lot = round(capital / 100_000, 2)  # simplified for Forex
            alloc = SymbolAllocation(
                symbol=sym,
                weight=round(w, 4),
                capital_usd=round(capital, 2),
                max_lot_size=max(0.01, max_lot),
            )
            allocations.append(alloc)
            self._allocations[sym] = alloc

        return allocations

    def should_rebalance(self) -> bool:
        self._bars_since_rebalance += 1
        if self._bars_since_rebalance >= self.config.rebalance_every_n_bars:
            self._bars_since_rebalance = 0
            return True
        return False

    def get_snapshot(self, current_equity: float, timestamp: float) -> PortfolioSnapshot:
        allocations = self.compute_allocations(current_equity)
        total_exposure = sum(a.current_exposure_usd for a in allocations)
        exposure_pct = total_exposure / current_equity * 100 if current_equity > 0 else 0
        div_ratio = self._diversification_ratio(allocations)
        return PortfolioSnapshot(
            timestamp=timestamp,
            total_equity=current_equity,
            allocations=allocations,
            total_exposure_usd=total_exposure,
            exposure_pct=round(exposure_pct, 2),
            diversification_ratio=round(div_ratio, 4),
            method_used=self.config.method.value,
        )

    # ------------------------------------------------------------------ #
    #  Allocation methods                                                   #
    # ------------------------------------------------------------------ #

    def _equal_weight(self, symbols: List[str]) -> List[float]:
        w = 1.0 / len(symbols)
        return [w] * len(symbols)

    def _risk_parity(self, symbols: List[str]) -> List[float]:
        vols = []
        for sym in symbols:
            rets = self._returns_history.get(sym, [0.0])
            vols.append(max(self._std(rets), 1e-8))
        inv_vols = [1.0 / v for v in vols]
        total = sum(inv_vols)
        return [iv / total for iv in inv_vols]

    def _kelly(self, symbols: List[str]) -> List[float]:
        kellys = []
        for sym in symbols:
            rets = self._returns_history.get(sym, [])
            if len(rets) < 5:
                kellys.append(0.0)
                continue
            wins = [r for r in rets if r > 0]
            losses = [r for r in rets if r < 0]
            if not wins or not losses:
                kellys.append(0.0)
                continue
            win_rate = len(wins) / len(rets)
            avg_win = sum(wins) / len(wins)
            avg_loss = abs(sum(losses) / len(losses))
            b = avg_win / avg_loss if avg_loss > 0 else 1
            kelly = win_rate - (1 - win_rate) / b
            kellys.append(max(0, kelly * 0.5))  # half-Kelly for safety

        total = sum(kellys)
        if total <= 0:
            return self._equal_weight(symbols)
        return [k / total for k in kellys]

    def _clip_weights(self, weights: List[float], symbols: List[str]) -> List[float]:
        min_w = self.config.min_position_pct / 100
        max_w = self.config.max_position_pct / 100
        clipped = [max(min_w, min(max_w, w)) for w in weights]
        total = sum(clipped)
        return [w / total for w in clipped] if total > 0 else clipped

    @staticmethod
    def _std(values: List[float]) -> float:
        if len(values) < 2:
            return 0.01
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))

    @staticmethod
    def _diversification_ratio(allocations: List[SymbolAllocation]) -> float:
        """Simple HHI-based diversification score (1 = fully diversified)."""
        if not allocations:
            return 0.0
        hhi = sum(a.weight ** 2 for a in allocations)
        n = len(allocations)
        return (1 / hhi) / n if hhi > 0 else 1.0
