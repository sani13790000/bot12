"""
backend/risk/volatility_filter.py
Galaxy Vast AI Trading Platform — Volatility Filter Gate

Blocks trading when ATR-based volatility is outside acceptable bounds.
Uses canonical NewsEvent from news_filter.py (single source of truth).
"""
from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("risk.volatility_filter")

# ── Single source of truth for NewsEvent ─────────────────────────────────────
try:
    from .news_filter import NewsEvent  # canonical
except ImportError:
    @dataclass
    class NewsEvent:  # type: ignore[no-redef]
        symbol:    str
        impact:    str   = "HIGH"
        timestamp: float = 0.0


@dataclass
class VolatilityConfig:
    max_atr_multiplier:  float = 3.0
    min_atr_multiplier:  float = 0.3
    news_pre_minutes:    int   = 30
    news_post_minutes:   int   = 15
    enabled:             bool  = True


@dataclass
class VolatilityCheckResult:
    can_trade:    bool
    reason:       str   = ""
    atr_ratio:    float = 1.0
    news_blocked: bool  = False


class VolatilityFilter:
    """
    Volatility gate: blocks on extreme ATR and pre/post high-impact news windows.
    """

    def __init__(self, config: Optional[VolatilityConfig] = None) -> None:
        self._cfg         = config or VolatilityConfig()
        self._news_events: List[NewsEvent]         = []
        self._atr_history: Dict[str, List[float]]  = {}
        self._lock:        Optional[asyncio.Lock]   = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def name(self) -> str:
        return "VolatilityFilter"

    def load_news_events(self, events: List[Any]) -> None:
        """Load news events — accepts canonical NewsEvent from news_filter."""
        self._news_events = [e for e in events if isinstance(e, NewsEvent)]
        logger.debug("VolatilityFilter loaded news", count=len(self._news_events))

    async def update_atr(self, symbol: str, atr: float) -> None:
        """Update ATR history for a symbol (rolling 100 samples)."""
        async with self._get_lock():
            hist = self._atr_history.setdefault(symbol, [])
            hist.append(atr)
            if len(hist) > 100:
                self._atr_history[symbol] = hist[-100:]

    async def check(self, symbol: str, current_atr: float) -> VolatilityCheckResult:
        """Check if volatility is within acceptable bounds."""
        if not self._cfg.enabled:
            return VolatilityCheckResult(can_trade=True, reason="disabled")

        async with self._get_lock():
            hist = list(self._atr_history.get(symbol, []))

        if len(hist) >= 10:
            window = hist[-20:]
            normal_atr = sum(window) / len(window)
            if normal_atr > 0:
                ratio = current_atr / normal_atr
                if ratio > self._cfg.max_atr_multiplier:
                    return VolatilityCheckResult(
                        can_trade=False,
                        reason=f"ATR too high: {ratio:.2f}x > max {self._cfg.max_atr_multiplier}x",
                        atr_ratio=ratio,
                    )
                if ratio < self._cfg.min_atr_multiplier:
                    return VolatilityCheckResult(
                        can_trade=False,
                        reason=f"ATR too low: {ratio:.2f}x < min {self._cfg.min_atr_multiplier}x",
                        atr_ratio=ratio,
                    )

        now = datetime.datetime.utcnow()
        sym_upper = symbol[:3].upper()
        for event in self._news_events:
            if sym_upper not in event.symbol.upper():
                continue
            try:
                event_time = datetime.datetime.utcfromtimestamp(event.timestamp)
            except (OSError, OverflowError, ValueError):
                continue
            delta_min = (event_time - now).total_seconds() / 60.0
            if -self._cfg.news_post_minutes <= delta_min <= self._cfg.news_pre_minutes:
                return VolatilityCheckResult(
                    can_trade=False,
                    reason=f"News blackout: {event.symbol} in {delta_min:.1f}min",
                    news_blocked=True,
                )

        return VolatilityCheckResult(can_trade=True, reason="ok")
