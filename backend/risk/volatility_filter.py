"""
backend/risk/volatility_filter.py
====================================
Senior Quant Developer - Surgical Refactor
FIX #1  Real News Filter gate
FIX #2  Robust ATR baseline (median/EMA spike-resistant)
FIX #3  Symbol-specific volatility thresholds
FIX #6  Fail-closed mode (configurable)
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

# FIX #7: canonical FailMode from single source of truth
try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fail_mode
except ImportError:  # pragma: no cover
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce_fail_mode(v) -> "FailMode":  # type: ignore[misc]
        return v if isinstance(v, FailMode) else FailMode(str(v).upper())


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
    low:     float
    high:    float
    extreme: float

    def __post_init__(self) -> None:
        if not (0 < self.low < self.high < self.extreme):
            raise ValueError(
                f"SymbolThresholds require 0 < low({self.low}) < "
                f"high({self.high}) < extreme({self.extreme})"
            )

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.low, self.high, self.extreme)


# Default per-symbol thresholds (34 symbols)
_DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
    # Forex majors
    "EURUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "NZDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    # Forex minors
    "EURGBP": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURAUD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURNZD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPAUD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPNZD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    # Metals
    "XAUUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "XAGUSD": SymbolThresholds(low=0.6, high=1.9, extreme=3.2),
    "XPTUSD": SymbolThresholds(low=0.6, high=1.9, extreme=3.2),
    # Crypto
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
    # Energy
    "USOIL":  SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "UKOIL":  SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
}

# Aliases (broker / common names)
_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD": "XAUUSD", "SILVER": "XAGUSD", "PLATINUM": "XPTUSD",
    "BTC": "BTCUSD", "ETH": "ETHUSD", "LTC": "LTCUSD", "XRP": "XRPUSD",
    "DAX": "GER40", "DAX40": "GER40", "FTSE": "UK100",
    "DOW": "US30", "SP500": "US500", "SPX500": "US500",
    "NIKKEI": "JPN225", "ASX200": "AUS200", "WTI": "USOIL", "BRENT": "UKOIL",
    "NASDAQ": "NAS100",
}


@dataclass
class VolatilityFilterConfig:
    """
    Configuration for VolatilityFilter.

    FIX #2: atr_estimator selects robust baseline:
        'median' (default) - spike-resistant, recommended
        'ema'              - exponential, recent-weighted
        'mean'             - arithmetic (legacy)
    FIX #3: symbol_thresholds - optional per-symbol override (merged on default table)
    FIX #6: fail_mode - FAIL_CLOSED (default) or FAIL_OPEN
    """
    # ATR ratio thresholds (current ATR / avg ATR) — global fallback
    low_atr_ratio:      float = 0.5
    high_atr_ratio:     float = 2.0
    extreme_atr_ratio:  float = 3.5
    atr_period:         int   = 14
    # Spread as multiple of avg spread
    max_spread_multiplier: float = 3.0
    # Lot reduction in HIGH volatility
    high_vol_lot_multiplier: float = 0.6
    # News filter (FIX #1)
    news_block_minutes_before: int  = 30
    news_block_minutes_after:  int  = 15
    enable_news_filter:        bool = True
    # FIX #2: robust ATR estimator
    atr_estimator: str   = "median"   # 'median' | 'ema' | 'mean'
    ema_alpha:     float = 0.0        # 0.0 = auto (2/(N+1))
    atr_window_cap: int  = 100        # max bars kept
    # FIX #3: per-symbol threshold overrides (None = use full default table)
    symbol_thresholds: Optional[Dict[str, SymbolThresholds]] = None
    # FIX #6: fail_mode
    fail_mode: FailMode = FailMode.FAIL_CLOSED


@dataclass(frozen=True)
class VolatilityCheckResult:
    """Result of a volatility check."""
    can_trade:       bool
    level:           VolatilityLevel
    reason:          str
    atr_ratio:       float
    spread_ratio:    float
    lot_multiplier:  float
    current_atr:     float
    avg_atr:         float
    current_spread:  float
    avg_spread:      float


class VolatilityLevel(str, Enum):
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    EXTREME = "EXTREME"


class VolatilityFilter:
    """
    ATR-based volatility gate.

    FIX #1: Real news event gate.
    FIX #2: Robust ATR baseline (median/EMA).
    FIX #3: Per-symbol thresholds with automatic fallback.
    FIX #6: Configurable FAIL_CLOSED / FAIL_OPEN.
    FIX #7: Removed unused asyncio.Lock, stray imports.
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        # FIX #3: build threshold table once at init
        base = dict(_DEFAULT_SYMBOL_THRESHOLDS)
        if self._cfg.symbol_thresholds:
            base.update(self._cfg.symbol_thresholds)
        self._symbol_thresholds: Dict[str, SymbolThresholds] = base
        # FIX #1: news events list (thread-safe list append is GIL-protected)
        self._news_events: List[NewsEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str = "",
        now:            Optional[datetime] = None,
    ) -> VolatilityCheckResult:
        """Run all volatility checks.  Returns VolatilityCheckResult."""
        try:
            return self._check_inner(
                current_atr, atr_history, current_spread, avg_spread, symbol, now
            )
        except Exception as exc:
            logger.error(
                "VolatilityFilter.check() internal error symbol=%s: %s",
                symbol, exc, exc_info=True,
            )
            _fm = _coerce_fail_mode(getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED))
            if _fm is FailMode.FAIL_CLOSED:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason=f"FAIL_CLOSED: internal error - {exc}",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )
            logger.critical(
                "FAIL_OPEN: VolatilityFilter exception swallowed symbol=%s: %s",
                symbol, exc, exc_info=True,
            )
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.NORMAL,
                reason=f"FAIL_OPEN:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
                atr_ratio=1.0, spread_ratio=1.0, lot_multiplier=1.0,
                current_atr=current_atr, avg_atr=current_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

    # FIX #1 — news event management
    def add_news_event(self, event: NewsEvent) -> None:
        self._news_events.append(event)

    def load_news_events(self, events: List[NewsEvent]) -> None:
        for e in events:
            if isinstance(e, NewsEvent):
                self._news_events.append(e)

    def clear_news_events(self) -> None:
        self._news_events.clear()

    def upcoming_events(
        self, symbol: str = "", lookahead_minutes: int = 60
    ) -> List[NewsEvent]:
        """Return news events that would block trading on symbol within lookahead window."""
        if not self._cfg.enable_news_filter:
            return []
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() + lookahead_minutes * 60
        return [
            e for e in self._news_events
            if e.event_time.timestamp() <= cutoff
               and e.event_time.timestamp() >= now.timestamp()
               and self._currency_matches(e.currency, symbol)
        ]

    # FIX #3 — runtime threshold management
    def add_symbol_threshold(self, symbol: str, thresholds: SymbolThresholds) -> None:
        if not isinstance(thresholds, SymbolThresholds):
            raise TypeError(f"thresholds must be SymbolThresholds, got {type(thresholds)}")
        self._symbol_thresholds[symbol.upper().strip()] = thresholds

    def remove_symbol_threshold(self, symbol: str) -> bool:
        key = symbol.upper().strip()
        if key in self._symbol_thresholds:
            del self._symbol_thresholds[key]
            return True
        return False

    def get_thresholds(self, symbol: str) -> Tuple[float, float, float]:
        return self._thresholds(symbol)

    def list_symbol_thresholds(self) -> Dict[str, SymbolThresholds]:
        return dict(self._symbol_thresholds)

    # ------------------------------------------------------------------
    # ATR calculations
    # ------------------------------------------------------------------

    def calculate_atr(
        self,
        highs:  List[float],
        lows:   List[float],
        closes: List[float],
    ) -> List[float]:
        """
        Wilder smoothed ATR series.
        Initial seed = arithmetic mean of first <period> TRs (intentional).
        """
        if len(highs) < 2:
            return []
        trs: List[float] = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i]  - closes[i - 1]),
            )
            trs.append(tr)
        period = self._cfg.atr_period
        if len(trs) < period:
            return trs
        atrs: List[float] = [sum(trs[:period]) / period]
        for i in range(period, len(trs)):
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
        return atrs

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_inner(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str = "",
        now:            Optional[datetime] = None,
    ) -> VolatilityCheckResult:
        """Core check logic (no exception handling — caller wraps)."""
        def _result(
            can_trade: bool,
            level: VolatilityLevel,
            reason: str,
            lot_mul: float,
        ) -> VolatilityCheckResult:
            return VolatilityCheckResult(
                can_trade=can_trade, level=level, reason=reason,
                atr_ratio=atr_ratio, spread_ratio=spread_ratio,
                lot_multiplier=lot_mul,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        # --- news gate (FIX #1) ---
        if self._cfg.enable_news_filter and symbol and self._news_events:
            blocked = self._check_news(symbol, now)
            if blocked:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason="NEWS_EVENT_BLOCK",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )

        # --- ATR baseline (FIX #2) ---
        window = atr_history[-self._cfg.atr_window_cap:] if atr_history else []
        if window:
            avg_atr = self._avg_atr(window)
        else:
            avg_atr = current_atr

        atr_ratio    = current_atr / avg_atr if avg_atr > 0 else 1.0
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0

        # threshold lookup (FIX #3)
        low_t, high_t, extreme_t = self._thresholds(symbol)

        if spread_ratio >= self._cfg.max_spread_multiplier:
            return _result(False, VolatilityLevel.EXTREME,
                           f"SPREAD_SPIKE {spread_ratio:.1f}x avg (>{self._cfg.max_spread_multiplier}x)",
                           0.0)
        if atr_ratio >= extreme_t:
            return _result(False, VolatilityLevel.EXTREME,
                           f"EXTREME_VOLATILITY ATR={atr_ratio:.1f}x (>{extreme_t}x)", 0.0)
        if atr_ratio >= high_t:
            return _result(True, VolatilityLevel.HIGH,
                           f"HIGH_VOLATILITY ATR={atr_ratio:.1f}x => lot x{self._cfg.high_vol_lot_multiplier}",
                           self._cfg.high_vol_lot_multiplier)
        if atr_ratio < low_t:
            return _result(True, VolatilityLevel.LOW,
                           f"LOW_VOLATILITY ATR={atr_ratio:.1f}x", 1.0)
        return _result(True, VolatilityLevel.NORMAL, "NORMAL_VOLATILITY", 1.0)

    def _avg_atr(self, window: List[float]) -> float:
        """FIX #2: Robust ATR baseline — median (default), EMA, or mean."""
        if not window:
            return 0.0
        estimator = getattr(self._cfg, "atr_estimator", "median")
        if estimator == "median":
            n = len(window)
            s = sorted(window)
            mid = n // 2
            return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
        if estimator == "ema":
            alpha = (
                self._cfg.ema_alpha
                if self._cfg.ema_alpha > 0
                else 2.0 / (len(window) + 1)
            )
            ema = window[0]
            for v in window[1:]:
                ema = alpha * v + (1.0 - alpha) * ema
            return ema
        # mean (legacy fallback)
        return sum(window) / len(window)

    def _thresholds(self, symbol: str) -> Tuple[float, float, float]:
        """FIX #3: Resolve per-symbol thresholds with fallback chain."""
        if not symbol:
            return (self._cfg.low_atr_ratio,
                    self._cfg.high_atr_ratio,
                    self._cfg.extreme_atr_ratio)
        key = symbol.upper().strip()
        # 1. exact match
        t = self._symbol_thresholds.get(key)
        if t:
            return t.as_tuple()
        # 2. alias
        alias = _SYMBOL_ALIASES.get(key)
        if alias:
            t = self._symbol_thresholds.get(alias)
            if t:
                return t.as_tuple()
        # 3. broker suffix strip
        for trim in range(1, 4):
            candidate = key[:-trim]
            t = self._symbol_thresholds.get(candidate)
            if t:
                return t.as_tuple()
        # 4. config globals
        return (self._cfg.low_atr_ratio,
                self._cfg.high_atr_ratio,
                self._cfg.extreme_atr_ratio)

    def _check_news(
        self, symbol: str, now: Optional[datetime] = None
    ) -> bool:
        """FIX #1: Return True if trading is blocked by a news event."""
        if now is None:
            now = datetime.now(timezone.utc)
        before_s = self._cfg.news_block_minutes_before * 60
        after_s  = self._cfg.news_block_minutes_after  * 60
        for event in self._news_events:
            if not self._currency_matches(event.currency, symbol):
                continue
            diff_s = (event.event_time - now).total_seconds()
            if -after_s <= diff_s <= before_s:
                return True
        return False

    @staticmethod
    def _currency_matches(currency: str, symbol: str) -> bool:
        c = currency.upper()
        if c == "ALL":
            return True
        s = symbol.upper()
        return c in s


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_vol_filter: Optional[VolatilityFilter] = None


def get_volatility_filter(
    config: Optional[VolatilityFilterConfig] = None,
) -> VolatilityFilter:
    """Return shared VolatilityFilter instance (lazy init)."""
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter(config)
    return _vol_filter
