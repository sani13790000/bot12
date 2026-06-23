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


class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


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
                f"SymbolThresholds requires 0 < low < high < extreme; "
                f"got low={self.low}, high={self.high}, extreme={self.extreme}"
            )

    def as_tuple(self) -> Tuple[float, float, float]:
        return self.low, self.high, self.extreme


# FIX #3: curated default table - 34 symbols
_DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
    "EURUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "NZDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "USDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURGBP": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "EURCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "GBPJPY": SymbolThresholds(low=0.6, high=2.0, extreme=3.5),
    "GBPCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "CADJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "CHFJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDCAD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "AUDCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "NZDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
    "XAUUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "XAGUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "XPTUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "BTCUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "ETHUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "LTCUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "XRPUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
    "US30":   SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "NAS100": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "US500":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "GER40":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "UK100":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "JPN225": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "AUS200": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    "USOIL":  SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
    "UKOIL":  SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
}

# FIX #3: broker symbol aliases -> canonical
_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD":    "XAUUSD",
    "SILVER":  "XAGUSD",
    "XAUUSDT": "XAUUSD",
    "XAGUSDT": "XAGUSD",
    "BTC":     "BTCUSD",
    "ETH":     "ETHUSD",
    "DOW":     "US30",
    "SP500":   "US500",
    "SPX500":  "US500",
    "NDX100":  "NAS100",
    "DAX":     "GER40",
    "DAX40":   "GER40",
    "FTSE":    "UK100",
    "FTSE100": "UK100",
    "NIKKEI":  "JPN225",
    "WTI":     "USOIL",
    "BRENT":   "UKOIL",
}


@dataclass
class VolatilityFilterConfig:
    low_atr_ratio:     float = 0.5
    high_atr_ratio:    float = 2.0
    extreme_atr_ratio: float = 3.5
    atr_period:        int   = 14
    max_spread_multiplier:   float = 3.0
    high_vol_lot_multiplier: float = 0.6
    enable_news_filter:        bool  = True
    news_block_minutes_before: int   = 30
    news_block_minutes_after:  int   = 15
    atr_estimator: str   = "median"
    ema_alpha:     float = 0.1
    # FIX #3: partial override merged with _DEFAULT_SYMBOL_THRESHOLDS at init
    symbol_thresholds: Optional[Dict[str, SymbolThresholds]] = None
    fail_mode: FailMode = FailMode.FAIL_CLOSED


class VolatilityLevel(str, Enum):
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class VolatilityCheckResult:
    can_trade:        bool
    level:            VolatilityLevel
    reason:           str
    atr_ratio:        float
    spread_ratio:     float
    lot_multiplier:   float
    current_atr:      float
    avg_atr:          float
    current_spread:   float
    avg_spread:       float
    news_blocked:     bool = False
    news_event_title: str  = ""


class VolatilityFilter:
    """
    ATR-based volatility gate.
    FIX #1: Real news-event gate.
    FIX #2: avg_atr uses median by default (spike-resistant).
    FIX #3: Per-symbol ATR thresholds (34 symbols, aliases, runtime API).
    FIX #6: Fail-closed on exception.
    FIX #7: No unused asyncio.Lock.
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        self._news_events: List[NewsEvent] = []
        # FIX #3: seed from defaults, merge caller overrides
        self._symbol_thresholds: Dict[str, SymbolThresholds] = dict(_DEFAULT_SYMBOL_THRESHOLDS)
        if self._cfg.symbol_thresholds:
            self._symbol_thresholds.update(self._cfg.symbol_thresholds)

    # FIX #3: runtime API
    def add_symbol_threshold(self, symbol: str, thresholds: SymbolThresholds) -> None:
        if not isinstance(thresholds, SymbolThresholds):
            raise TypeError(f"thresholds must be SymbolThresholds, got {type(thresholds)}")
        self._symbol_thresholds[symbol.upper()] = thresholds

    def remove_symbol_threshold(self, symbol: str) -> bool:
        removed = self._symbol_thresholds.pop(symbol.upper(), None)
        return removed is not None

    def get_thresholds(self, symbol: str) -> Tuple[float, float, float]:
        return self._thresholds(symbol)

    def list_symbol_thresholds(self) -> Dict[str, SymbolThresholds]:
        return dict(self._symbol_thresholds)

    # FIX #1: news management
    def load_news_events(self, events: List[NewsEvent]) -> None:
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]

    def add_news_event(self, event: NewsEvent) -> None:
        self._news_events.append(event)

    def clear_news_events(self) -> None:
        self._news_events.clear()

    def _check_news(self, symbol: str) -> Optional[VolatilityCheckResult]:
        if not self._cfg.enable_news_filter or not self._news_events:
            return None
        try:
            now = datetime.now(timezone.utc)
            sym_upper = symbol.upper()
            sym_currencies: set = set()
            if len(sym_upper) == 6:
                sym_currencies = {sym_upper[:3], sym_upper[3:]}
            elif len(sym_upper) > 3:
                sym_currencies = {sym_upper[:3]}
            before_s = self._cfg.news_block_minutes_before * 60
            after_s  = self._cfg.news_block_minutes_after  * 60
            for ev in self._news_events:
                ev_ccy = ev.currency.upper()
                if ev_ccy != "ALL" and ev_ccy not in sym_currencies and ev_ccy != sym_upper:
                    continue
                ev_time = ev.event_time
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                diff_s = (now - ev_time).total_seconds()
                if -before_s <= diff_s <= after_s:
                    logger.warning("VolatilityFilter news block: %s %s", ev.title, ev.currency)
                    return VolatilityCheckResult(
                        can_trade=False, level=VolatilityLevel.EXTREME,
                        reason="NEWS_EVENT_BLOCK",
                        atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                        current_atr=0.0, avg_atr=0.0,
                        current_spread=0.0, avg_spread=0.0,
                        news_blocked=True, news_event_title=ev.title,
                    )
        except Exception as exc:
            logger.warning("VolatilityFilter: news check failed (%s) - continuing", exc)
        return None

    def _avg_atr(self, atr_history: List[float], current_atr: float) -> float:
        """FIX #2: median(default)/ema(config alpha)/mean(legacy)."""
        window = atr_history[-self._cfg.atr_period:] if atr_history else []
        if not window:
            return current_atr
        estimator = self._cfg.atr_estimator
        if estimator == "median":
            n = len(window)
            s = sorted(window)
            mid = n // 2
            return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
        if estimator == "ema":
            alpha = self._cfg.ema_alpha if self._cfg.ema_alpha > 0 else 2.0 / (len(window) + 1)
            ema = window[0]
            for val in window[1:]:
                ema = alpha * val + (1.0 - alpha) * ema
            return ema
        return sum(window) / len(window)

    def _thresholds(self, symbol: str) -> Tuple[float, float, float]:
        """FIX #3: exact -> alias -> suffix strip -> config globals."""
        sym = symbol.upper().strip() if symbol else ""
        t = self._symbol_thresholds.get(sym)
        if t is not None:
            return t.as_tuple()
        canonical = _SYMBOL_ALIASES.get(sym)
        if canonical:
            t = self._symbol_thresholds.get(canonical)
            if t is not None:
                return t.as_tuple()
        for trim in range(1, 4):
            candidate = symbol.upper()[:-trim] if len(symbol) > trim else ""
            if candidate:
                t = self._symbol_thresholds.get(candidate)
                if t is not None:
                    return t.as_tuple()
        return (self._cfg.low_atr_ratio, self._cfg.high_atr_ratio, self._cfg.extreme_atr_ratio)

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
            fail_mode = getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED)
            if fail_mode == FailMode.FAIL_CLOSED:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason=f"FAIL_CLOSED: internal error - {exc}",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.NORMAL,
                reason=f"FAIL_OPEN: internal error ignored - {exc}",
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
        news_block = self._check_news(symbol)
        if news_block is not None:
            return news_block
        avg_atr      = self._avg_atr(atr_history, current_atr)
        atr_ratio    = current_atr / avg_atr if avg_atr > 0 else 1.0
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0
        low_thr, high_thr, extreme_thr = self._thresholds(symbol)

        def _result(can_trade, level, reason, lot_multiplier):
            return VolatilityCheckResult(
                can_trade=can_trade, level=level, reason=reason,
                atr_ratio=atr_ratio, spread_ratio=spread_ratio,
                lot_multiplier=lot_multiplier,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        if spread_ratio >= self._cfg.max_spread_multiplier:
            return _result(False, VolatilityLevel.EXTREME,
                           f"SPREAD_SPIKE {spread_ratio:.1f}x avg", 0.0)
        if atr_ratio >= extreme_thr:
            return _result(False, VolatilityLevel.EXTREME,
                           f"EXTREME_VOLATILITY ATR={atr_ratio:.2f}x (>{extreme_thr}x)", 0.0)
        if atr_ratio >= high_thr:
            return _result(True, VolatilityLevel.HIGH,
                           f"HIGH_VOLATILITY ATR={atr_ratio:.2f}x",
                           self._cfg.high_vol_lot_multiplier)
        if atr_ratio < low_thr:
            return _result(True, VolatilityLevel.LOW,
                           f"LOW_VOLATILITY ATR={atr_ratio:.2f}x", 1.0)
        return _result(True, VolatilityLevel.NORMAL, "NORMAL_VOLATILITY", 1.0)

    def calculate_atr(self, highs: List[float], lows: List[float],
                      closes: List[float]) -> List[float]:
        """Wilder ATR. Arithmetic mean seed is intentional (standard Wilder init)."""
        if len(highs) < 2:
            return []
        trs: List[float] = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        period = self._cfg.atr_period
        if len(trs) < period:
            return trs
        atrs: List[float] = [sum(trs[:period]) / period]
        for i in range(period, len(trs)):
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
        return atrs


_vol_filter: Optional[VolatilityFilter] = None


def get_volatility_filter(config: Optional[VolatilityFilterConfig] = None) -> VolatilityFilter:
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter(config)
    return _vol_filter
