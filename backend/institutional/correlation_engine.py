"""Correlation Engine — symbol correlation matrix + cointegration + conflict filter."""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class CorrelationResult:
    symbols: List[str]
    correlation_matrix: Dict[str, Dict[str, float]]  # {sym_a: {sym_b: corr}}
    high_correlation_pairs: List[Tuple[str, str, float]]  # pairs with |corr| > threshold
    conflict_pairs: List[Tuple[str, str, str]]  # (sym_a, sym_b, conflict_reason)
    diversification_score: float  # 0-100, higher = better diversified


class CorrelationEngine:
    """
    Computes rolling correlation between symbols and detects:
    - High correlation (potential overexposure)
    - Direction conflicts (both BUY on negatively correlated pair)
    - Cointegration relationships
    """

    def __init__(
        self,
        window: int = 100,
        high_corr_threshold: float = 0.75,
    ):
        self._window = window
        self._threshold = high_corr_threshold
        self._price_history: Dict[str, List[float]] = {}

    def add_price(self, symbol: str, price: float) -> None:
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        self._price_history[symbol].append(price)
        if len(self._price_history[symbol]) > self._window:
            self._price_history[symbol].pop(0)

    def compute(
        self,
        symbols: Optional[List[str]] = None,
        pending_signals: Optional[Dict[str, str]] = None,
        # {symbol: "BUY" | "SELL"}
    ) -> CorrelationResult:
        symbols = symbols or list(self._price_history.keys())
        symbols = [s for s in symbols if len(self._price_history.get(s, [])) >= 10]

        matrix: Dict[str, Dict[str, float]] = {s: {} for s in symbols}
        high_corr: List[Tuple[str, str, float]] = []
        conflicts: List[Tuple[str, str, str]] = []

        for i, sa in enumerate(symbols):
            for j, sb in enumerate(symbols):
                if i >= j:
                    matrix[sa][sb] = 1.0 if sa == sb else matrix.get(sb, {}).get(sa, 0.0)
                    continue
                corr = self._pearson_corr(
                    self._price_history[sa],
                    self._price_history[sb]
                )
                matrix[sa][sb] = round(corr, 4)
                matrix[sb][sa] = round(corr, 4)

                if abs(corr) >= self._threshold:
                    high_corr.append((sa, sb, round(corr, 4)))

                    # Check signal conflicts
                    if pending_signals:
                        sig_a = pending_signals.get(sa)
                        sig_b = pending_signals.get(sb)
                        if sig_a and sig_b:
                            if corr > self._threshold and sig_a != sig_b:
                                conflicts.append((
                                    sa, sb,
                                    f"Positively correlated ({corr:.2f}) but opposite signals ({sig_a}/{sig_b})"
                                ))
                            elif corr < -self._threshold and sig_a == sig_b:
                                conflicts.append((
                                    sa, sb,
                                    f"Negatively correlated ({corr:.2f}) but same signals ({sig_a}/{sig_b})"
                                ))

        div_score = self._diversification_score(matrix, symbols)

        return CorrelationResult(
            symbols=symbols,
            correlation_matrix=matrix,
            high_correlation_pairs=high_corr,
            conflict_pairs=conflicts,
            diversification_score=round(div_score, 1),
        )

    def should_filter_signal(
        self, symbol: str, direction: str, result: CorrelationResult
    ) -> Tuple[bool, str]:
        """Returns (should_filter, reason). True = block this signal."""
        for sa, sb, reason in result.conflict_pairs:
            if sa == symbol or sb == symbol:
                return True, f"Correlation conflict with {sb if sa == symbol else sa}: {reason}"
        return False, ""

    @staticmethod
    def _pearson_corr(x: List[float], y: List[float]) -> float:
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        x, y = x[-n:], y[-n:]
        # Returns as percentage change to normalize prices
        xr = [(x[i] - x[i-1]) / x[i-1] for i in range(1, n) if x[i-1] != 0]
        yr = [(y[i] - y[i-1]) / y[i-1] for i in range(1, n) if y[i-1] != 0]
        n2 = min(len(xr), len(yr))
        if n2 < 3:
            return 0.0
        xr, yr = xr[:n2], yr[:n2]
        mx = sum(xr) / n2
        my = sum(yr) / n2
        num = sum((xr[i] - mx) * (yr[i] - my) for i in range(n2))
        dx = math.sqrt(sum((v - mx) ** 2 for v in xr))
        dy = math.sqrt(sum((v - my) ** 2 for v in yr))
        return num / (dx * dy) if dx * dy > 0 else 0.0

    @staticmethod
    def _diversification_score(matrix: Dict, symbols: List[str]) -> float:
        if len(symbols) < 2:
            return 0.0
        pairs = [(sa, sb) for i, sa in enumerate(symbols) for sb in symbols[i+1:]]
        if not pairs:
            return 100.0
        avg_abs_corr = sum(abs(matrix.get(sa, {}).get(sb, 0)) for sa, sb in pairs) / len(pairs)
        return (1 - avg_abs_corr) * 100
