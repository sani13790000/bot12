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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class VolatilityLevel(str, Enum):
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class NewsEvent:
    time:     datetime
    symbol:   str
    impact:   str   # "HIGH" | "MEDIUM" | "LOW"
    title:    str   = ""


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
    news_blocked:   bool          = False
    news_event:     Optional[NewsEvent] = None


@dataclass
class SymbolThresholds:
    """Per-symbol ATR ratio thresholds."""
    low:     float
    high:    float
    extreme: float

    def __post_init__(self) -> None:
        if not (0 < self.low < self.high < self.extreme):
            raise ValueError(
                f"SymbolThresholds must satisfy 0 < low < high < extreme; "
                f"got low={self.low}, high={self.high}, extreme={self.extreme}"
            )

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.low, self.high, self.extreme)


# ---------------------------------------------------------------------------
# Default symbol threshold table (FIX #3)
# ---------------------------------------------------------------------------

_DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
    # Forex majors
    "EURUSD": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "GBPUSD": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    "USDJPY": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "USDCHF": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "AUDUSD": SymbolThresholds(low=0.55, high=2.1,  extreme=3.6),
    "USDCAD": SymbolThresholds(low=0.55, high=2.1,  extreme=3.6),
    "NZDUSD": SymbolThresholds(low=0.55, high=2.1,  extreme=3.6),
    # Forex minors
    "EURGBP": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "EURJPY": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    "GBPJPY": SymbolThresholds(low=0.65, high=2.3,  extreme=4.0),
    "AUDJPY": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    "EURCHF": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "GBPCHF": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    "AUDNZD": SymbolThresholds(low=0.55, high=2.1,  extreme=3.6),
    "AUDCAD": SymbolThresholds(low=0.55, high=2.1,  extreme=3.6),
    "CADCHF": SymbolThresholds(low=0.5,  high=2.0,  extreme=3.5),
    "CADJPY": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    "NZDJPY": SymbolThresholds(low=0.6,  high=2.2,  extreme=3.8),
    # Metals
    "XAUUSD": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "XAGUSD": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "XPTUSD": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    # Crypto
    "BTCUSD": SymbolThresholds(low=0.8,  high=1.5,  extreme=2.2),
    "ETHUSD": SymbolThresholds(low=0.8,  high=1.5,  extreme=2.2),
    "LTCUSD": SymbolThresholds(low=0.8,  high=1.5,  extreme=2.2),
    "XRPUSD": SymbolThresholds(low=0.8,  high=1.5,  extreme=2.2),
    # Equity indices
    "US30":   SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "NAS100": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "US500":  SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "GER40":  SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "UK100":  SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "JPN225": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "AUS200": SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    # Energy
    "USOIL":  SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
    "UKOIL":  SymbolThresholds(low=0.7,  high=1.8,  extreme=3.0),
}

_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD":   "XAUUSD",
    "SILVER": "XAGUSD",
    "PLAT":   "XPTUSD",
    "BTC":    "BTCUSD",
    "ETH":    "ETHUSD",
    "LTC":    "LTCUSD",
    "XRP":    "XRPUSD",
    "DAX":    "GER40",
    "DAX40":  "GER40",
    "FTSE":   "UK100",
    "SP500":  "US500",
    "SPX500": "US500",
    "NIKKEI": "JPN225",
    "WTI":    "USOIL",
    "BRENT":  "UKOIL",
    "DOW":    "US30",
    "NASDAQ": "NAS100",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class VolatilityFilterConfig:
    # ATR-based thresholds (global defaults)
    low_volatility_threshold:     float = 0.5
    high_volatility_threshold:    float = 2.0
    extreme_volatility_threshold: float = 3.5
    # Spread
    max_spread_multiplier:        float = 2.5
    # ATR history
    atr_history_bars:             int   = 20
    # News blackout
    news_blackout_minutes_before: int   = 30
    news_blackout_minutes_after:  int   = 30
    high_impact_only:             bool  = True
    # Per-symbol overrides (FIX #3)
    symbol_thresholds: Optional[Dict[str, SymbolThresholds]] = None
    # FIX #6: fail mode
    fail_mode: FailMode = FailMode.FAIL_CLOSED


# ---------------------------------------------------------------------------
# VolatilityFilter
# ---------------------------------------------------------------------------

class VolatilityFilter:
    """Filter trades based on ATR volatility, spread, and news events."""

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        self._atr_history: List[float] = []
        self._news_events: List[NewsEvent] = []
        # Build symbol threshold table (FIX #3)
        self._symbol_thresholds: Dict[str, SymbolThresholds] = dict(_DEFAULT_SYMBOL_THRESHOLDS)
        if self._cfg.symbol_thresholds:
            self._symbol_thresholds.update({
                k.upper(): v for k, v in self._cfg.symbol_thresholds.items()
            })
        # FIX-6 + FIX-7: cache fail_mode ONCE in __init__ (not recomputed on every exception)
        self._fail_mode: FailMode = _coerce_fm(
            getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED)
        )

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

    def set_news_events(self, events: List[NewsEvent]) -> None:
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]

    def clear_news_events(self) -> None:
        self._news_events.clear()

    # ------------------------------------------------------------------
    # Symbol threshold management (FIX #3 runtime API)
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
    # Internal: threshold resolution
    # ------------------------------------------------------------------

    def _thresholds(self, symbol: str) -> Tuple[float, float, float]:
        sym = symbol.upper().strip()
        # 1. exact match
        t = self._symbol_thresholds.get(sym)
        if t:
            return t.as_tuple()
        # 2. alias
        alias = _SYMBOL_ALIASES.get(sym)
        if alias:
            t = self._symbol_thresholds.get(alias)
            if t:
                return t.as_tuple()
        # 3. broker suffix strip (up to 4 chars)
        for trim in range(1, 5):
            candidate = sym[:-trim] if len(sym) > trim else ""
            if not candidate:
                break
            t = self._symbol_thresholds.get(candidate)
            if t:
                return t.as_tuple()
            a = _SYMBOL_ALIASES.get(candidate)
            if a:
                t2 = self._symbol_thresholds.get(a)
                if t2:
                    return t2.as_tuple()
        # 4. global config defaults
        return (
            self._cfg.low_volatility_threshold,
            self._cfg.high_volatility_threshold,
            self._cfg.extreme_volatility_threshold,
        )

    # ------------------------------------------------------------------
    # Public check
    # ------------------------------------------------------------------

    def check(
        self,
        current_atr:    float,
        atr_history:    Optional[List[float]] = None,
        current_spread: float = 0.0,
        avg_spread:     float = 0.0,
        symbol:         str   = "",
        # Legacy keyword aliases
        atr_values:     Optional[List[float]] = None,
        spread:         Optional[float]       = None,
    ) -> VolatilityCheckResult:
        """Return VolatilityCheckResult. Never raises (fail_mode controls on exception)."""
        # Resolve legacy kwargs
        if atr_values is not None:
            atr_history = atr_values
        if spread is not None:
            current_spread = spread
        try:
            return self._check_inner(current_atr, atr_history, current_spread, avg_spread, symbol)
        except Exception as exc:
            logger.error("VolatilityFilter.check exception (symbol=%s): %s", symbol, exc, exc_info=True)
            # FIX-6 + FIX-7: use cached self._fail_mode (set once in __init__)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return VolatilityCheckResult(
                    can_trade=False, level=VolatilityLevel.EXTREME,
                    reason=f"FAIL_CLOSED:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )
            logger.critical(
                "FAIL_OPEN: VolatilityFilter exception swallowed, trade ALLOWED. symbol=%s fail_mode=%s",
                symbol, self._fail_mode
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
        atr_history:    Optional[List[float]],
        current_spread: float,
        avg_spread:     float,
        symbol:         str,
    ) -> VolatilityCheckResult:
        """Core logic -- called by check() inside try/except."""
        now = datetime.now(timezone.utc)

        # --- news check (FIX #1) ---
        if symbol:
            sym_upper = symbol.upper()
            for event in self._news_events:
                if event.symbol.upper() != sym_upper:
                    continue
                if self._cfg.high_impact_only and event.impact.upper() != "HIGH":
                    continue
                mins_before = (event.time - now).total_seconds() / 60
                mins_after  = (now - event.time).total_seconds() / 60
                if -self._cfg.news_blackout_minutes_before <= mins_before <= 0 or \
                   0 <= mins_after <= self._cfg.news_blackout_minutes_after:
                    return VolatilityCheckResult(
                        can_trade=False, level=VolatilityLevel.EXTREME,
                        reason=f"NEWS_BLACKOUT:{event.title[:40]}",
                        atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                        current_atr=current_atr, avg_atr=0.0,
                        current_spread=current_spread, avg_spread=avg_spread,
                        news_blocked=True, news_event=event,
                    )

        # --- ATR baseline (FIX #2) ---
        history = list(atr_history) if atr_history else list(self._atr_history)
        if history:
            sorted_h = sorted(history)
            n = len(sorted_h)
            trim = max(1, n // 10)
            trimmed = sorted_h[trim:-trim] if n > 2 * trim else sorted_h
            avg_atr = sum(trimmed) / len(trimmed) if trimmed else current_atr
        else:
            avg_atr = current_atr

        atr_ratio = (current_atr / avg_atr) if avg_atr > 0 else 1.0

        # --- spread check ---
        spread_ratio = (current_spread / avg_spread) if avg_spread > 0 else 1.0
        if spread_ratio > self._cfg.max_spread_multiplier:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"SPREAD_TOO_HIGH:ratio={spread_ratio:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        # --- symbol thresholds (FIX #3) ---
        low_thr, high_thr, extreme_thr = self._thresholds(symbol)

        if atr_ratio >= extreme_thr:
            return VolatilityCheckResult(
                can_trade=False, level=VolatilityLevel.EXTREME,
                reason=f"EXTREME_VOLATILITY:atr_ratio={atr_ratio:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=0.0,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        if atr_ratio >= high_thr:
            lot_mult = max(0.25, 1.0 - (atr_ratio - high_thr) / (extreme_thr - high_thr))
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.HIGH,
                reason=f"HIGH_VOLATILITY:atr_ratio={atr_ratio:.2f}:lot_mult={lot_mult:.2f}",
                atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=lot_mult,
                current_atr=current_atr, avg_atr=avg_atr,
                current_spread=current_spread, avg_spread=avg_spread,
            )

        return VolatilityCheckResult(
            can_trade=True, level=VolatilityLevel.NORMAL,
            reason="NORMAL_VOLATILITY",
            atr_ratio=atr_ratio, spread_ratio=spread_ratio, lot_multiplier=1.0,
            current_atr=current_atr, avg_atr=avg_atr,
            current_spread=current_spread, avg_spread=avg_spread,
        )


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_vol_filter: Optional[VolatilityFilter] = None


def get_volatility_filter(
    config: Optional[VolatilityFilterConfig] = None,
) -> VolatilityFilter:
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter(config)
    return _vol_filter
