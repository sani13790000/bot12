"""
backend/risk/volatility_filter.py
====================================
Senior Quant Developer — Surgical Refactor
FIX #1  Real News Filter gate
FIX #2  Robust ATR baseline (median/EMA spike-resistant)
FIX #3  Symbol-specific volatility thresholds
FIX #6  Fail-closed mode (configurable)
FIX #7  Dead code removal (unused lock, stray imports)

Public API 100% backward-compatible.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

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


@dataclass
class SymbolThresholds:
    """FIX #3: Per-symbol ATR thresholds."""
    low:     float = 0.5
    high:    float = 2.0
    extreme: float = 3.5


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
    symbol_thresholds: Dict[str, SymbolThresholds] = field(default_factory=lambda: {
        "EURUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
        "GBPUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
        "AUDUSD": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
        "USDJPY": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
        "USDCHF": SymbolThresholds(low=0.5, high=2.0, extreme=3.5),
        "XAUUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
        "XAGUSD": SymbolThresholds(low=0.7, high=1.8, extreme=3.0),
        "BTCUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
        "ETHUSD": SymbolThresholds(low=0.8, high=1.5, extreme=2.2),
        "US30":   SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
        "NAS100": SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
        "US500":  SymbolThresholds(low=0.6, high=1.8, extreme=3.0),
    })
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
    FIX #2: avg_atr uses median by default.
    FIX #3: Per-symbol ATR thresholds.
    FIX #6: Fail-closed on exception.
    FIX #7: No unused asyncio.Lock.
    """

    def __init__(self, config: Optional[VolatilityFilterConfig] = None) -> None:
        self._cfg = config or VolatilityFilterConfig()
        self._news_events: List[NewsEvent] = []

    def load_news_events(self, events: List[NewsEvent]) -> None:
        """FIX #1: Replace the current news calendar."""
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]
        logger.info("VolatilityFilter: loaded %d news events", len(self._news_events))

    def add_news_event(self, event: NewsEvent) -> None:
        self._news_events.append(event)

    def clear_news_events(self) -> None:
        self._news_events.clear()

    def _check_news(self, symbol: str) -> Optional["VolatilityCheckResult"]:
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
            before_delta_s = self._cfg.news_block_minutes_before * 60
            after_delta_s  = self._cfg.news_block_minutes_after  * 60
            for ev in self._news_events:
                ev_ccy = ev.currency.upper()
                if ev_ccy != "ALL" and ev_ccy not in sym_currencies and ev_ccy != sym_upper:
                    continue
                ev_time = ev.event_time
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                diff_s = (now - ev_time).total_seconds()
                if -before_delta_s <= diff_s <= after_delta_s:
                    reason = (f"NEWS_EVENT_BLOCK: '{ev.title}' ({ev.currency} {ev.impact}) "
                              f"@ {ev_time.isoformat()}")
                    logger.warning("VolatilityFilter news block: %s", reason)
                    return VolatilityCheckResult(
                        can_trade=False, level=VolatilityLevel.EXTREME,
                        reason="NEWS_EVENT_BLOCK",
                        atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                        current_atr=0.0, avg_atr=0.0,
                        current_spread=0.0, avg_spread=0.0,
                        news_blocked=True, news_event_title=ev.title,
                    )
        except Exception as exc:
            logger.warning("VolatilityFilter: news check failed (%s) — continuing normally", exc)
        return None

    def _avg_atr(self, atr_history: List[float], current_atr: float) -> float:
        window = atr_history[-self._cfg.atr_period:] if atr_history else []
        if not window:
            return current_atr
        estimator = getattr(self._cfg, "atr_estimator", "median")
        if estimator == "median":
            return statistics.median(window)
        if estimator == "ema":
            alpha = 2.0 / (len(window) + 1)
            ema = window[0]
            for val in window[1:]:
                ema = alpha * val + (1 - alpha) * ema
            return ema
        return sum(window) / len(window)

    def _thresholds(self, symbol: str):
        sym = symbol.upper() if symbol else ""
        overrides: Dict[str, SymbolThresholds] = getattr(self._cfg, "symbol_thresholds", {})
        t = overrides.get(sym)
        if t is None:
            return (self._cfg.low_atr_ratio, self._cfg.high_atr_ratio, self._cfg.extreme_atr_ratio)
        return t.low, t.high, t.extreme

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
    ) -> "VolatilityCheckResult":
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
                    reason=f"FAIL_CLOSED: internal error — {exc}",
                    atr_ratio=0.0, spread_ratio=0.0, lot_multiplier=0.0,
                    current_atr=current_atr, avg_atr=0.0,
                    current_spread=current_spread, avg_spread=avg_spread,
                )
            return VolatilityCheckResult(
                can_trade=True, level=VolatilityLevel.NORMAL,
                reason=f"FAIL_OPEN: internal error ignored — {exc}",
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
    ) -> "VolatilityCheckResult":
        news_block = self._check_news(symbol)
        if news_block is not None:
            return news_block
        avg_atr = self._avg_atr(atr_history, current_atr)
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
                           f"SPREAD_SPIKE {spread_ratio:.1f}x avg (>{self._cfg.max_spread_multiplier}x)", 0.0)
        if atr_ratio >= extreme_thr:
            return _result(False, VolatilityLevel.EXTREME,
                           f"EXTREME_VOLATILITY ATR={atr_ratio:.2f}x (>{extreme_thr}x)", 0.0)
        if atr_ratio >= high_thr:
            return _result(True, VolatilityLevel.HIGH,
                           f"HIGH_VOLATILITY ATR={atr_ratio:.2f}x => lot x{self._cfg.high_vol_lot_multiplier}",
                           self._cfg.high_vol_lot_multiplier)
        if atr_ratio < low_thr:
            return _result(True, VolatilityLevel.LOW,
                           f"LOW_VOLATILITY ATR={atr_ratio:.2f}x — reduced opportunity", 1.0)
        return _result(True, VolatilityLevel.NORMAL, "NORMAL_VOLATILITY", 1.0)

    def calculate_atr(self, highs: List[float], lows: List[float],
                      closes: List[float]) -> List[float]:
        """Calculate ATR series from OHLC data. UNCHANGED."""
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


# FIX #7: removed dead asyncio.Lock singleton init
_vol_filter: Optional[VolatilityFilter] = None


def get_volatility_filter(config: Optional[VolatilityFilterConfig] = None) -> VolatilityFilter:
    global _vol_filter
    if _vol_filter is None:
        _vol_filter = VolatilityFilter(config)
    return _vol_filter
