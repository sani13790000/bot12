"""backend/risk/volatility_filter.py
FIX #1  Real News Filter gate
FIX #2  Robust ATR baseline (median/EMA spike-resistant)
FIX #3  Symbol-specific volatility thresholds
FIX #6  Fail-closed mode (configurable) - FailMode from canonical fail_mode.py
FIX #7  Dead code removal:
        - removed dead 'field' import from dataclasses (no field() usage)
        - cache _fail_mode in __init__ instead of re-computing in except block

Public API 100% backward-compatible.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
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


class VolatilityLevel(str, Enum):
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class SymbolThresholds:
    """FIX #3: Per-symbol volatility thresholds."""
    low:     float = 0.5
    high:    float = 2.0
    extreme: float = 3.5

    def __post_init__(self) -> None:
        if not (0 < self.low < self.high < self.extreme):
            raise ValueError(
                f"Thresholds must satisfy 0 < low < high < extreme, "
                f"got low={self.low} high={self.high} extreme={self.extreme}"
            )

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.low, self.high, self.extreme)


_DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
    # Forex majors
    "EURUSD": SymbolThresholds(0.5, 2.0, 3.5),
    "GBPUSD": SymbolThresholds(0.6, 2.2, 3.8),
    "USDJPY": SymbolThresholds(0.5, 2.0, 3.5),
    "USDCHF": SymbolThresholds(0.5, 1.9, 3.3),
    "AUDUSD": SymbolThresholds(0.5, 2.0, 3.5),
    "USDCAD": SymbolThresholds(0.5, 2.0, 3.5),
    "NZDUSD": SymbolThresholds(0.5, 2.0, 3.5),
    # Forex minors
    "EURGBP": SymbolThresholds(0.5, 1.8, 3.2),
    "EURJPY": SymbolThresholds(0.6, 2.2, 3.8),
    "GBPJPY": SymbolThresholds(0.7, 2.5, 4.2),
    "EURCHF": SymbolThresholds(0.5, 1.8, 3.2),
    "EURAUD": SymbolThresholds(0.6, 2.2, 3.8),
    "EURCAD": SymbolThresholds(0.5, 2.0, 3.5),
    "GBPCHF": SymbolThresholds(0.6, 2.2, 3.8),
    "GBPAUD": SymbolThresholds(0.7, 2.5, 4.2),
    "GBPCAD": SymbolThresholds(0.6, 2.2, 3.8),
    "AUDCAD": SymbolThresholds(0.5, 1.9, 3.3),
    "AUDCHF": SymbolThresholds(0.5, 1.9, 3.3),
    "AUDJPY": SymbolThresholds(0.6, 2.2, 3.8),
    # Metals
    "XAUUSD": SymbolThresholds(0.7, 1.8, 3.0),
    "XAGUSD": SymbolThresholds(0.8, 2.0, 3.5),
    "XPTUSD": SymbolThresholds(0.7, 1.8, 3.0),
    # Crypto
    "BTCUSD": SymbolThresholds(0.8, 1.5, 2.2),
    "ETHUSD": SymbolThresholds(0.9, 1.7, 2.5),
    "LTCUSD": SymbolThresholds(0.9, 1.7, 2.5),
    "XRPUSD": SymbolThresholds(1.0, 1.8, 2.8),
    # Equity indices
    "US30":   SymbolThresholds(0.6, 1.8, 3.0),
    "NAS100": SymbolThresholds(0.6, 1.8, 3.0),
    "US500":  SymbolThresholds(0.6, 1.8, 3.0),
    "GER40":  SymbolThresholds(0.6, 1.8, 3.0),
    "UK100":  SymbolThresholds(0.6, 1.8, 3.0),
    "JPN225": SymbolThresholds(0.6, 1.8, 3.0),
    "AUS200": SymbolThresholds(0.6, 1.8, 3.0),
    # Energy
    "USOIL":  SymbolThresholds(0.7, 2.0, 3.5),
    "UKOIL":  SymbolThresholds(0.7, 2.0, 3.5),
}


@dataclass
class VolatilityFilterConfig:
    atr_history_bars:          int   = 14
    low_volatility_ratio:      float = 0.5
    high_volatility_ratio:     float = 2.0
    extreme_volatility_ratio:  float = 3.5
    max_spread_ratio:          float = 3.0
    atr_estimator:             str   = "median"
    ema_alpha:                 float = 0.0
    enable_news_filter:        bool  = True
    news_block_minutes_before: int   = 30
    news_block_minutes_after:  int   = 15
    symbol_thresholds:         Optional[Dict[str, SymbolThresholds]] = None
    fail_mode:                 FailMode = FailMode.FAIL_CLOSED


@dataclass
class VolatilityCheckResult:
    can_trade:     bool
    level:         VolatilityLevel
    reason:        str
    atr_ratio:     float
    spread_ratio:  float
    lot_multiplier: float
    current_atr:   float
    avg_atr:       float
    current_spread: float
    avg_spread:    float
    symbol:        str = ""


class VolatilityFilter:
    """
    FIX #1: News event gate.
    FIX #2: Median/EMA ATR estimator.
    FIX #3: Per-symbol thresholds.
    FIX #6: Fail-closed on exception (configurable).
    FIX #7: _fail_mode cached once in __init__.
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        self._atr_history: List[float] = []
        self._news_events: List[NewsEvent] = []
        # FIX #6 + #7: cache fail_mode once at construction (not re-computed per except)
        self._fail_mode: FailMode = _coerce_fm(
            getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED)
        )
        # Build symbol threshold table
        self._symbol_thresholds: Dict[str, SymbolThresholds] = dict(_DEFAULT_SYMBOL_THRESHOLDS)
        if self._cfg.symbol_thresholds:
            self._symbol_thresholds.update({
                k.upper(): v for k, v in self._cfg.symbol_thresholds.items()
            })

    def update_atr(self, atr_value: float) -> None:
        if atr_value > 0:
            self._atr_history.append(atr_value)
            max_bars = self._cfg.atr_history_bars * 2
            if len(self._atr_history) > max_bars:
                self._atr_history = self._atr_history[-max_bars:]

    def add_news_event(self, event: NewsEvent) -> None:
        self._news_events.append(event)

    def load_news_events(self, events: List[NewsEvent]) -> None:
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]

    def clear_news_events(self) -> None:
        self._news_events.clear()

    def add_symbol_threshold(self, symbol: str, thresholds: SymbolThresholds) -> None:
        if not isinstance(thresholds, SymbolThresholds):
            raise TypeError(f"Expected SymbolThresholds, got {type(thresholds)}")
        self._symbol_thresholds[symbol.upper()] = thresholds

    def remove_symbol_threshold(self, symbol: str) -> bool:
        return self._symbol_thresholds.pop(symbol.upper(), None) is not None

    def get_thresholds(self, symbol: str) -> Tuple[float, float, float]:
        return self._thresholds(symbol.upper())

    def list_symbol_thresholds(self) -> Dict[str, SymbolThresholds]:
        return dict(self._symbol_thresholds)

    def _thresholds(self, symbol: str) -> Tuple[float, float, float]:
        st = self._symbol_thresholds.get(symbol)
        if st:
            return st.as_tuple()
        return (
            self._cfg.low_volatility_ratio,
            self._cfg.high_volatility_ratio,
            self._cfg.extreme_volatility_ratio,
        )

    def _avg_atr(self, window: List[float]) -> float:
        if not window:
            return 0.0
        estimator = self._cfg.atr_estimator
        if estimator == "median":
            n   = len(window)
            s   = sorted(window)
            mid = n // 2
            return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
        if estimator == "ema":
            alpha = self._cfg.ema_alpha if self._cfg.ema_alpha > 0 else 2.0 / (len(window) + 1)
            ema = window[0]
            for v in window[1:]:
                ema = alpha * v + (1 - alpha) * ema
            return ema
        return sum(window) / len(window)

    def _check_news(self, now: datetime) -> Optional[VolatilityCheckResult]:
        if not self._cfg.enable_news_filter or not self._news_events:
            return None
        before_s = self._cfg.news_block_minutes_before * 60
        after_s  = self._cfg.news_block_minutes_after  * 60
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        for ev in self._news_events:
            et = ev.event_time
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            diff_s = (now - et).total_seconds()
            if -before_s <= diff_s <= after_s:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason="NEWS_EVENT_BLOCK",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=0.0, avg_atr=0.0,
                    current_spread=0.0, avg_spread=0.0,
                )
        return None

    def check(
        self,
        current_atr:    float,
        atr_history:    Optional[List[float]] = None,
        current_spread: float = 0.0,
        avg_spread:     float = 0.0,
        symbol:         str   = "",
        *,
        atr_values:     Optional[List[float]] = None,
        spread:         Optional[float] = None,
    ) -> VolatilityCheckResult:
        if atr_history is None:
            atr_history = list(self._atr_history)
        if atr_values is not None:
            atr_history = atr_values
        if spread is not None:
            current_spread = spread
        try:
            return self._check_inner(current_atr, atr_history, current_spread, avg_spread, symbol)
        except Exception as exc:
            logger.error("VolatilityFilter.check exception (symbol=%s): %s", symbol, exc, exc_info=True)
            # FIX #7: use cached self._fail_mode (set in __init__), not re-computed each call
            if self._fail_mode is FailMode.FAIL_CLOSED:
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
        now = datetime.now(timezone.utc)
        news_block = self._check_news(now)
        if news_block is not None:
            return news_block

        sym_upper = symbol.upper() if symbol else ""
        low_r, high_r, extreme_r = self._thresholds(sym_upper)

        window   = atr_history[-self._cfg.atr_history_bars:] if atr_history else [current_atr]
        avg_atr  = self._avg_atr(window) if window else current_atr
        atr_ratio = (current_atr / avg_atr) if avg_atr > 0 else 1.0

        spread_ratio = (current_spread / avg_spread) if avg_spread > 0 else 1.0

        if atr_ratio >= extreme_r:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"EXTREME_VOLATILITY: atr_ratio={atr_ratio:.2f} >= {extreme_r}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread, symbol=sym_upper,
            )

        if spread_ratio > self._cfg.max_spread_ratio:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"SPREAD_TOO_HIGH: ratio={spread_ratio:.2f} > {self._cfg.max_spread_ratio}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread, symbol=sym_upper,
            )

        if atr_ratio >= high_r:
            lot_mult = max(0.1, 1.0 - (atr_ratio - high_r) / (extreme_r - high_r))
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.HIGH,
                reason=f"HIGH_VOLATILITY: atr_ratio={atr_ratio:.2f} lot_mult={lot_mult:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=lot_mult,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread, symbol=sym_upper,
            )

        return VolatilityCheckResult(
            can_trade=True, level=VolatilityLevel.NORMAL,
            reason="",
            atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=1.0,
            current_atr=current_atr, avg_atr=avg_atr,
            current_spread=current_spread, avg_spread=avg_spread, symbol=sym_upper,
        )


def get_volatility_filter(config: Optional[VolatilityFilterConfig] = None) -> VolatilityFilter:
    return VolatilityFilter(config=config)
