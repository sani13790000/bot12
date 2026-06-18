"""Galaxy Vast AI Trading Platform — Correlation Engine.

- Correlation matrix across symbols
- Cointegration testing
- Conflict detection between signals
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class CorrelationResult:
    symbol_pair: Tuple[str, str]
    correlation: float
    p_value: float
    cointegrated: bool = False
    conflict: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_pair": list(self.symbol_pair),
            "correlation": round(self.correlation, 4),
            "p_value": round(self.p_value, 6),
            "cointegrated": self.cointegrated,
            "conflict": self.conflict,
        }


class CorrelationEngine:
    """Compute correlations and detect conflicting trade signals."""

    def __init__(self, correlation_threshold: float = 0.7, coint_pvalue: float = 0.05):
        self.correlation_threshold = correlation_threshold
        self.coint_pvalue = coint_pvalue

    def build_returns_matrix(self, price_series: Dict[str, pd.Series]) -> pd.DataFrame:
        """Convert price series to daily log returns."""
        returns = {}
        for sym, series in price_series.items():
            returns[sym] = np.log(series / series.shift(1))
        df = pd.DataFrame(returns).dropna()
        return df

    def correlation_matrix(self, returns: pd.DataFrame) -> pd.DataFrame:
        return returns.corr()

    def analyze_pairs(
        self,
        price_series: Dict[str, pd.Series],
        signals: Optional[List[Dict[str, Any]]] = None,
    ) -> List[CorrelationResult]:
        returns = self.build_returns_matrix(price_series)
        symbols = list(returns.columns)
        results = []
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                sym_a, sym_b = symbols[i], symbols[j]
                corr = returns[sym_a].corr(returns[sym_b])
                _, p_value = stats.pearsonr(returns[sym_a], returns[sym_b])
                coint_score, coint_p = self._cointegration_test(
                    price_series[sym_a].dropna(), price_series[sym_b].dropna()
                )
                coint = coint_p < self.coint_pvalue
                conflict = self._detect_conflict(sym_a, sym_b, signals) if signals else False
                results.append(CorrelationResult(
                    symbol_pair=(sym_a, sym_b),
                    correlation=corr,
                    p_value=p_value,
                    cointegrated=coint,
                    conflict=conflict,
                ))
        return results

    def _cointegration_test(self, a: pd.Series, b: pd.Series) -> Tuple[float, float]:
        try:
            from statsmodels.tsa.stattools import coint
            score, p_value, _ = coint(a, b)
            return score, p_value
        except Exception:
            return 0.0, 1.0

    @staticmethod
    def _detect_conflict(sym_a: str, sym_b: str, signals: List[Dict[str, Any]]) -> bool:
        dir_a = None
        dir_b = None
        for sig in signals:
            if sig.get("symbol") == sym_a:
                dir_a = str(sig.get("direction", "")).upper()
            if sig.get("symbol") == sym_b:
                dir_b = str(sig.get("direction", "")).upper()
        if dir_a and dir_b and dir_a != dir_b:
            return True
        return False

    def filter_conflicting_signals(
        self,
        signals: List[Dict[str, Any]],
        price_series: Dict[str, pd.Series],
    ) -> List[Dict[str, Any]]:
        """Remove the lower-confidence signal from each correlated conflicting pair."""
        pairs = self.analyze_pairs(price_series, signals)
        conflicts = {tuple(p.symbol_pair) for p in pairs if p.conflict and abs(p.correlation) >= self.correlation_threshold}
        if not conflicts:
            return signals

        to_remove = set()
        for a, b in conflicts:
            sig_a = next((s for s in signals if s.get("symbol") == a), None)
            sig_b = next((s for s in signals if s.get("symbol") == b), None)
            if sig_a and sig_b:
                low = sig_a if sig_a.get("confidence", 0) < sig_b.get("confidence", 0) else sig_b
                to_remove.add(low.get("symbol"))

        return [s for s in signals if s.get("symbol") not in to_remove]
