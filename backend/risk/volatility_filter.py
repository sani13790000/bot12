"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Volatility Filter — ATR-based market condition gate
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class VolatilityLevel(str, Enum):
    LOW     = "LOW"      # ATR < low threshold  → cautious
    NORMAL  = "NORMAL"   # ATR in normal range   → trade freely
    HIGH    = "HIGH"     # ATR > high threshold  → reduce size
    EXTREME = "EXTREME"  # ATR > extreme thresh  → NO TRADE


@dataclass
class VolatilityFilterConfig:
    # ATR ratio thresholds (current ATR / avg ATR)
    low_atr_ratio: float = 0.5        # below this = LOW
    high_atr_ratio: float = 2.0       # above this = HIGH
    extreme_atr_ratio: float = 3.5    # above this = EXTREME (block)
    atr_period: int = 14
    # Spread as multiple of avg spread
    max_spread_multiplier: float = 3.0
    # Lot reduction in HIGH volatility
    high_vol_lot_multiplier: float = 0.6
    # Block trading during news (minutes before/after)
    news_block_minutes_before: int = 30
    news_block_minutes_after: int = 15
    enable_news_filter: bool = True


@dataclass
class VolatilityCheckResult:
    can_trade: bool
    level: VolatilityLevel
    reason: str
    atr_ratio: float        # current / average
    spread_ratio: float     # current / average
    lot_multiplier: float   # 1.0 = normal, <1.0 = reduce
    current_atr: float
    avg_atr: float
    current_spread: float
    avg_spread: float


class VolatilityFilter:
    """
    ATR-based volatility gate:
    - Blocks trading during extreme volatility
    - Reduces position size in high volatility
    - Filters abnormal spread conditions
    - Optional news event blocking
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None):
        self._cfg = config or VolatilityFilterConfig()

    def check(
        self,
        current_atr: float,
        atr_history: List[float],    # last N ATR values
        current_spread: float,
        avg_spread: float,
    ) -> VolatilityCheckResult:

        # Calculate average ATR
        if atr_history:
            avg_atr = sum(atr_history[-self._cfg.atr_period:]) / min(
                len(atr_history), self._cfg.atr_period
            )
        else:
            avg_atr = current_atr

        atr_ratio    = current_atr / avg_atr if avg_atr > 0 else 1.0
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0

        # ① Spread filter
        if spread_ratio >= self._cfg.max_spread_multiplier:
            return VolatilityCheckResult(
                can_trade=False,
                level=VolatilityLevel.EXTREME,
                reason=f"SPREAD_SPIKE {spread_ratio:.1f}x avg (>{self._cfg.max_spread_multiplier}x)",
                atr_ratio=atr_ratio,
                spread_ratio=spread_ratio,
                lot_multiplier=0.0,
                current_atr=current_atr,
                avg_atr=avg_atr,
                current_spread=current_spread,
                avg_spread=avg_spread,
            )

        # ② Extreme volatility
        if atr_ratio >= self._cfg.extreme_atr_ratio:
            return VolatilityCheckResult(
                can_trade=False,
                level=VolatilityLevel.EXTREME,
                reason=f"EXTREME_VOLATILITY ATR={atr_ratio:.1f}x (>{self._cfg.extreme_atr_ratio}x)",
                atr_ratio=atr_ratio,
                spread_ratio=spread_ratio,
                lot_multiplier=0.0,
                current_atr=current_atr,
                avg_atr=avg_atr,
                current_spread=current_spread,
                avg_spread=avg_spread,
            )

        # ③ High volatility — reduce lot
        if atr_ratio >= self._cfg.high_atr_ratio:
            return VolatilityCheckResult(
                can_trade=True,
                level=VolatilityLevel.HIGH,
                reason=f"HIGH_VOLATILITY ATR={atr_ratio:.1f}x → lot x{self._cfg.high_vol_lot_multiplier}",
                atr_ratio=atr_ratio,
                spread_ratio=spread_ratio,
                lot_multiplier=self._cfg.high_vol_lot_multiplier,
                current_atr=current_atr,
                avg_atr=avg_atr,
                current_spread=current_spread,
                avg_spread=avg_spread,
            )

        # ④ Low volatility — trade but note
        if atr_ratio < self._cfg.low_atr_ratio:
            return VolatilityCheckResult(
                can_trade=True,
                level=VolatilityLevel.LOW,
                reason=f"LOW_VOLATILITY ATR={atr_ratio:.1f}x — reduced opportunity",
                atr_ratio=atr_ratio,
                spread_ratio=spread_ratio,
                lot_multiplier=1.0,
                current_atr=current_atr,
                avg_atr=avg_atr,
                current_spread=current_spread,
                avg_spread=avg_spread,
            )

        # ✅ Normal
        return VolatilityCheckResult(
            can_trade=True,
            level=VolatilityLevel.NORMAL,
            reason="NORMAL_VOLATILITY",
            atr_ratio=atr_ratio,
            spread_ratio=spread_ratio,
            lot_multiplier=1.0,
            current_atr=current_atr,
            avg_atr=avg_atr,
            current_spread=current_spread,
            avg_spread=avg_spread,
        )

    def calculate_atr(self, highs: List[float], lows: List[float],
                      closes: List[float]) -> List[float]:
        """Calculate ATR series from OHLC data."""
        if len(highs) < 2:
            return []
        trs, atrs = [], []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i]  - closes[i-1]),
            )
            trs.append(tr)
        period = self._cfg.atr_period
        if len(trs) < period:
            return trs
        atrs.append(sum(trs[:period]) / period)
        for i in range(period, len(trs)):
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
        return atrs


_vol_filter: Optional[VolatilityFilter] = None

def get_volatility_filter() -> VolatilityFilter:
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter()
    return _vol_filter
