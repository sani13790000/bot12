"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Correlation Filter — prevents over-exposure to correlated pairs
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Static Correlation Matrix (daily avg, major pairs) ──────────
# Values between -1.0 (inverse) and +1.0 (same direction)
CORRELATION_MATRIX: Dict[str, Dict[str, float]] = {
    "EURUSD": {"GBPUSD": 0.85, "AUDUSD": 0.72, "NZDUSD": 0.70,
               "USDCHF": -0.92, "USDJPY": -0.55, "USDCAD": -0.60,
               "XAUUSD": 0.30, "EURUSD": 1.0},
    "GBPUSD": {"EURUSD": 0.85, "AUDUSD": 0.65, "NZDUSD": 0.60,
               "USDCHF": -0.80, "USDJPY": -0.45, "USDCAD": -0.55,
               "XAUUSD": 0.25, "GBPUSD": 1.0},
    "AUDUSD": {"EURUSD": 0.72, "GBPUSD": 0.65, "NZDUSD": 0.92,
               "USDCHF": -0.68, "USDJPY": -0.40, "USDCAD": -0.50,
               "XAUUSD": 0.45, "AUDUSD": 1.0},
    "NZDUSD": {"EURUSD": 0.70, "GBPUSD": 0.60, "AUDUSD": 0.92,
               "USDCHF": -0.65, "USDJPY": -0.38, "USDCAD": -0.48,
               "XAUUSD": 0.40, "NZDUSD": 1.0},
    "USDCHF": {"EURUSD": -0.92, "GBPUSD": -0.80, "AUDUSD": -0.68,
               "NZDUSD": -0.65, "USDJPY": 0.50, "USDCAD": 0.55,
               "XAUUSD": -0.28, "USDCHF": 1.0},
    "USDJPY": {"EURUSD": -0.55, "GBPUSD": -0.45, "AUDUSD": -0.40,
               "NZDUSD": -0.38, "USDCHF": 0.50, "USDCAD": 0.40,
               "XAUUSD": -0.35, "USDJPY": 1.0},
    "USDCAD": {"EURUSD": -0.60, "GBPUSD": -0.55, "AUDUSD": -0.50,
               "NZDUSD": -0.48, "USDCHF": 0.55, "USDJPY": 0.40,
               "XAUUSD": -0.20, "USDCAD": 1.0},
    "XAUUSD": {"EURUSD": 0.30, "GBPUSD": 0.25, "AUDUSD": 0.45,
               "NZDUSD": 0.40, "USDCHF": -0.28, "USDJPY": -0.35,
               "USDCAD": -0.20, "XAUUSD": 1.0},
    "XAGUSD": {"XAUUSD": 0.87, "EURUSD": 0.28, "AUDUSD": 0.42, "XAGUSD": 1.0},
    "BTCUSD": {"XAUUSD": 0.15, "ETHUSD": 0.92, "BTCUSD": 1.0},
    "ETHUSD": {"BTCUSD": 0.92, "ETHUSD": 1.0},
}


@dataclass
class CorrelationFilterConfig:
    max_correlated_exposure: float = 0.80   # block if |corr| > this
    correlation_penalty_threshold: float = 0.60  # apply penalty above this
    max_same_direction_corr_pairs: int = 2  # max highly corr pairs same dir
    risk_multiplier_high_corr: float = 0.5  # reduce lot by this if corr > threshold


@dataclass
class OpenPosition:
    symbol: str
    direction: str  # "BUY" or "SELL"
    risk_percent: float


@dataclass
class CorrelationCheckResult:
    can_trade: bool
    reason: str
    correlation_score: float        # highest |correlation| found
    correlated_pairs: List[str]
    adjusted_risk_percent: float    # risk after penalty
    risk_multiplier: float          # 1.0 = no change, <1.0 = reduced


class CorrelationFilter:
    """
    Prevents over-exposure to correlated currency pairs.
    Uses static correlation matrix + direction-aware logic.
    """

    def __init__(self, config: Optional[CorrelationFilterConfig] = None):
        self._cfg = config or CorrelationFilterConfig()

    def check(
        self,
        new_symbol: str,
        new_direction: str,
        open_positions: List[OpenPosition],
        base_risk_percent: float,
    ) -> CorrelationCheckResult:
        """Check if new trade is safe given open positions."""
        if not open_positions:
            return CorrelationCheckResult(
                can_trade=True,
                reason="NO_OPEN_POSITIONS",
                correlation_score=0.0,
                correlated_pairs=[],
                adjusted_risk_percent=base_risk_percent,
                risk_multiplier=1.0,
            )

        max_corr     = 0.0
        corr_pairs   = []
        same_dir_count = 0

        for pos in open_positions:
            corr = self._get_correlation(new_symbol, pos.symbol)
            if corr is None:
                continue
            abs_corr = abs(corr)
            if abs_corr > max_corr:
                max_corr = abs_corr

            # Direction-aware: EURUSD BUY + GBPUSD BUY = amplified risk
            effective_corr = corr
            if pos.direction != new_direction:
                effective_corr = -corr  # inverse position = actually diversifying

            if abs(effective_corr) >= self._cfg.correlation_penalty_threshold:
                corr_pairs.append(f"{pos.symbol}({corr:+.2f})")
                if effective_corr > 0:
                    same_dir_count += 1

        # ① BLOCK if max correlation exceeds threshold
        if max_corr >= self._cfg.max_correlated_exposure:
            return CorrelationCheckResult(
                can_trade=False,
                reason=f"HIGH_CORRELATION {max_corr:.2f} >= {self._cfg.max_correlated_exposure}",
                correlation_score=max_corr,
                correlated_pairs=corr_pairs,
                adjusted_risk_percent=0.0,
                risk_multiplier=0.0,
            )

        # ② BLOCK if too many same-direction correlated pairs
        if same_dir_count >= self._cfg.max_same_direction_corr_pairs:
            return CorrelationCheckResult(
                can_trade=False,
                reason=f"TOO_MANY_CORRELATED_PAIRS {same_dir_count} same-direction",
                correlation_score=max_corr,
                correlated_pairs=corr_pairs,
                adjusted_risk_percent=0.0,
                risk_multiplier=0.0,
            )

        # ③ Apply penalty if correlated pairs exist
        multiplier = 1.0
        if corr_pairs:
            multiplier = self._cfg.risk_multiplier_high_corr
        adj_risk = base_risk_percent * multiplier

        return CorrelationCheckResult(
            can_trade=True,
            reason="PASSED" if not corr_pairs else f"CORR_PENALTY x{multiplier}",
            correlation_score=max_corr,
            correlated_pairs=corr_pairs,
            adjusted_risk_percent=round(adj_risk, 3),
            risk_multiplier=multiplier,
        )

    def get_correlation(self, sym_a: str, sym_b: str) -> Optional[float]:
        return self._get_correlation(sym_a, sym_b)

    def _get_correlation(self, a: str, b: str) -> Optional[float]:
        a, b = a.upper(), b.upper()
        if a == b:
            return 1.0
        row = CORRELATION_MATRIX.get(a, {})
        if b in row:
            return row[b]
        row_b = CORRELATION_MATRIX.get(b, {})
        if a in row_b:
            return row_b[a]
        return None


_corr_filter: Optional[CorrelationFilter] = None

def get_correlation_filter() -> CorrelationFilter:
    global _corr_filter
    if _corr_filter is None:
        _corr_filter = CorrelationFilter()
    return _corr_filter
