"""
backend/risk/volatility_filter.py
====================================
Senior Quant Developer - Surgical Refactor
FIX #1  Real News Filter gate
FIX #2  Robust ATR baseline (median/EMA spike-resistant)
FIX #3  Symbol-specific volatility thresholds
FIX #6  Fail-closed mode (configurable) - FailMode from canonical fail_mode.py
FIX #7  Dead code removal (unused lock, stray imports)

Public API 100% backward-compatible.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("risk.volatility_filter")

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
except ImportError:
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"
    def _coerce_fm(v) -> "FailMode":
        if isinstance(v, FailMode): return v
        return FailMode(str(v).upper())


@dataclass
class NewsEvent:
    """FIX #1: Scheduled economic news event."""
    title:      str
    currency:   str
    impact:     str
    event_time: datetime


# ---------------------------------------------------------------------------
# FIX #3 - Symbol-specific volatility thresholds
# ---------------------------------------------------------------------------

@dataclass
class SymbolThresholds:
    """
    FIX #3: Per-symbol ATR ratio thresholds.

    Validation (enforced in __post_init__):
        low < high < extreme - any violation raises ValueError at construction
        time so misconfigured thresholds are caught early, not at runtime.
    """
    low:     float = 0.5
    high:    float = 2.0
    extreme: float = 3.5

    def __post_init__(self) -> None:
        if not (0 < self.low < self.high < self.extreme):
            raise ValueError(
                f"SymbolThresholds must satisfy 0 < low < high < extreme, "
                f"got low={self.low} high={self.high} extreme={self.extreme}"
            )

    def as_tuple(self) -> Tuple[float, float, float]:
        """Return (low, high, extreme) as a typed tuple."""
        return (self.low, self.high, self.extreme)


_DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
    # Forex majors
    "EURUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "NZDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    # Forex minors
    "EURGBP": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURAUD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURNZD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPAUD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPNZD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "NZDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "CADJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "CHFJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    # Metals (tighter - higher baseline volatility)
    "XAUUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "XAGUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "XPTUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    # Crypto (tightest - extreme volatility regime)
    "BTCUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "ETHUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "LTCUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "XRPUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    # Equity indices
    "US30":   SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "NAS100": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "US500":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "GER40":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "UK100":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "JPN225": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "AUS200": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
}

_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD":    "XAUUSD",
    "SILVER":  "XAGUSD",
    "BTC":     "BTCUSD",
    "ETH":     "ETHUSD",
    "DAX":     "GER40",
    "DAX40":   "GER40",
    "FTSE":    "UK100",
    "SP500":   "US500",
    "SPX500":  "US500",
    "NIKKEI":  "JPN225",
    "WTI":     "USOIL",
    "DOW":     "US30",
    "NASDAQ":  "NAS100",
}


class VolatilityLevel(str, Enum):
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class VolatilityCheckResult:
    can_trade:      bool
    level:          VolatilityLevel
    reason:         str
    atr_ratio:      float
    spread_ratio:   float
    lot_multiplier: float
    current_atr:    float
    avg_atr:        float
    current_spread: float
    avg_spread:     float


@dataclass
class VolatilityFilterConfig:
    # ATR history
    atr_history_bars:    int   = 14
    # Classification thresholds (global fallback - overridden per-symbol by symbol_thresholds)
    low_volatility_ratio:     float = 0.5
    high_volatility_ratio:    float = 2.0
    extreme_volatility_ratio: float = 3.5
    # ATR estimator: "median" (default, spike-robust), "ema", or "mean"
    atr_estimator: str   = "median"
    ema_alpha:     float = 0.0  # 0 = auto-compute from window size
    # Spread filter
    max_spread_ratio: float = 3.0
    # News filter
    enable_news_filter:         bool = True
    news_block_minutes_before:  int  = 30
    news_block_minutes_after:   int  = 15
    # FIX #3: Per-symbol thresholds (None = use _DEFAULT_SYMBOL_THRESHOLDS)
    symbol_thresholds: Optional[Dict[str, SymbolThresholds]] = None
    # FIX #6: Fail mode
    fail_mode: FailMode = FailMode.FAIL_CLOSED


class VolatilityFilter:
    """
    FIX #1: Real News Filter gate.
    FIX #2: Robust ATR baseline (median/EMA/mean estimator).
    FIX #3: Per-symbol volatility thresholds.
    FIX #6: Fail-closed on exception (configurable).
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        self._atr_history: List[float] = []
        self._news_events: List[NewsEvent] = []
        # Build symbol threshold table
        self._symbol_thresholds: Dict[str, SymbolThresholds] = dict(_DEFAULT_SYMBOL_THRESHOLDS)
        if self._cfg.symbol_thresholds:
            self._symbol_thresholds.update({
                k.upper(): v for k, v in self._cfg.symbol_thresholds.items()
            })

    # ------------------------------------------------------------------
    # ATR management
    # ------------------------------------------------------------------

    def update_atr(self, atr_value: float) -> None:
        """Add a new ATR sample to the rolling history."""
        if atr_value > 0:
            self._atr_history.append(atr_value)
            max_bars = self._cfg.atr_history_bars * 2
            if len(self._atr_history) > max_bars:
                self._atr_history = self._atr_history[-max_bars:]

    # ------------------------------------------------------------------
    # News event management
    # ------------------------------------------------------------------

    def add_news_event(self, event: NewsEvent) -> None:
        self._news_events.append(event)

    def load_news_events(self, events: List[NewsEvent]) -> None:
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]

    def clear_news_events(self) -> None:
        self._news_events.clear()

    # ------------------------------------------------------------------
    # Symbol threshold management (FIX #3)
    # ------------------------------------------------------------------

    def add_symbol_threshold(self, symbol: str, thresholds: SymbolThresholds) -> None:
        if not isinstance(thresholds, SymbolThresholds):
            raise TypeError(f"Expected SymbolThresholds, got {type(thresholds).__name__}")
        self._symbol_thresholds[symbol.upper()] = thresholds

    def remove_symbol_threshold(self, symbol: str) -> bool:
        key = symbol.upper()
        if key in self._symbol_thresholds:
            del self._symbol_thresholds[key]
            return True
        return False

    def get_thresholds(self, symbol: str) -> Tuple[float, float, float]:
        return self._thresholds(symbol)

    def list_symbol_thresholds(self) -> Dict[str, SymbolThresholds]:
        return dict(self._symbol_thresholds)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _thresholds(self, symbol: str) -> Tuple[float, float, float]:
        """Return (low, high, extreme) for a symbol with fallback chain."""
        sym = symbol.upper().strip()
        # 1. exact match
        t = self._symbol_thresholds.get(sym)
        if t is not None:
            return t.as_tuple()
        # 2. alias
        alias = _SYMBOL_ALIASES.get(sym)
        if alias:
            t = self._symbol_thresholds.get(alias)
            if t is not None:
                return t.as_tuple()
        # 3. broker suffix strip (1-3 chars)
        for trim in range(1, 4):
            candidate = sym[:-trim]
            t = self._symbol_thresholds.get(candidate)
            if t is not None:
                return t.as_tuple()
        # 4. global fallback
        return (
            self._cfg.low_volatility_ratio,
            self._cfg.high_volatility_ratio,
            self._cfg.extreme_volatility_ratio,
        )

    def _avg_atr(self, window: List[float]) -> float:
        """FIX #2: Robust ATR baseline. Estimator: median (default), ema, or mean."""
        if not window:
            return 0.0
        estimator = getattr(self._cfg, "atr_estimator", "median")
        if estimator == "ema":
            alpha = self._cfg.ema_alpha if self._cfg.ema_alpha > 0 else 2.0 / (len(window) + 1)
            ema = window[0]
            for v in window[1:]:
                ema = alpha * v + (1.0 - alpha) * ema
            return ema
        if estimator == "mean":
            return sum(window) / len(window)
        # default: median (spike-robust)
        n = len(window)
        s = sorted(window)
        mid = n // 2
        return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0

    def _check_news(self, symbol: str, now: datetime) -> Optional[str]:
        """FIX #1: Return block reason if current time is in a news window."""
        if not self._cfg.enable_news_filter or not self._news_events:
            return None
        sym_upper = symbol.upper()
        before_s = self._cfg.news_block_minutes_before * 60
        after_s  = self._cfg.news_block_minutes_after  * 60
        for event in self._news_events:
            try:
                et = event.event_time
                if et.tzinfo is None:
                    et = et.replace(tzinfo=timezone.utc)
                now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
                diff_s  = (now_utc - et).total_seconds()
                if not (-before_s <= diff_s <= after_s):
                    continue
                # Currency match
                ccy = event.currency.upper()
                if ccy == "ALL" or ccy in sym_upper:
                    return f"NEWS_EVENT_BLOCK:{event.title}:{event.currency}"
            except Exception as exc:
                logger.warning("Skipping bad NewsEvent: %s - %s", event, exc)
        return None

    # ------------------------------------------------------------------
    # Public check() - FIX #6: wrapped in try/except
    # ------------------------------------------------------------------

    def check(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str = "",
        *,
        atr_values:     Optional[List[float]] = None,
        spread:         Optional[float] = None,
    ) -> VolatilityCheckResult:
        if atr_values is not None:
            atr_history = atr_values
        if spread is not None:
            current_spread = spread
        try:
            return self._check_inner(current_atr, atr_history, current_spread, avg_spread, symbol)
        except Exception as exc:
            logger.error("VolatilityFilter.check exception (symbol=%s): %s", symbol, exc, exc_info=True)
            _fm = _coerce_fm(getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED))
            if _fm is FailMode.FAIL_CLOSED:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason=f"FAIL_CLOSED:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )
            logger.critical(
                "FAIL_OPEN: VolatilityFilter exception swallowed, trade ALLOWED. symbol=%s", symbol
            )
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.NORMAL,
                reason=f"FAIL_OPEN:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
                atr_ratio=1.0, spread_ratio=1.0, lot_multiplier=1.0,
                current_atr=current_atr, avg_atr=current_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

    def _check_inner(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str,
    ) -> VolatilityCheckResult:
        low_t, high_t, extreme_t = self._thresholds(symbol)

        history = atr_history if atr_history else self._atr_history
        avg_atr = self._avg_atr(history) if history else current_atr

        atr_ratio    = current_atr / avg_atr if avg_atr > 0 else 1.0
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0

        # News gate (FIX #1)
        news_reason = self._check_news(symbol, datetime.now(timezone.utc))
        if news_reason:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=news_reason,
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        # Spread gate
        if spread_ratio > self._cfg.max_spread_ratio:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"SPREAD_TOO_HIGH: ratio={spread_ratio:.2f} > {self._cfg.max_spread_ratio}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        # ATR classification
        if atr_ratio >= extreme_t:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"EXTREME_VOLATILITY: atr_ratio={atr_ratio:.2f} >= {extreme_t}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        if atr_ratio >= high_t:
            lot_multiplier = max(0.25, 1.0 - (atr_ratio - high_t) / (extreme_t - high_t))
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.HIGH,
                reason=f"HIGH_VOLATILITY: atr_ratio={atr_ratio:.2f}, lot_mult={lot_multiplier:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=lot_multiplier,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        if atr_ratio < low_t:
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.NORMAL,
                reason=f"LOW_VOLATILITY: atr_ratio={atr_ratio:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=1.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        return VolatilityCheckResult(
            can_trade=True, level=VolatilityLevel.NORMAL,
            reason="",
            atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=1.0,
            current_atr=current_atr, avg_atr=avg_atr,
            current_spread=current_spread, avg_spread=avg_spread,
        )


_vol_filter: Optional[VolatilityFilter] = None


def get_volatility_filter(config: Optional[VolatilityFilterConfig] = None) -> VolatilityFilter:
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter(config)
    return _vol_filter
