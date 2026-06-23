"""\nbackend/risk/news_filter.py\n============================\nFIX #1 — Real News Filter Gate (Production-Ready)\nSenior Quant Developer — Surgical Implementation\n\nDesign principles:\n  - Standalone module; VolatilityFilter delegates to this class\n  - Zero breaking changes to existing public API\n  - Fail-safe: any provider failure → log warning + continue\n  - Multi-event support with timezone-aware datetimes\n  - Provider abstraction: REST / file / manual injection\n"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol

logger = logging.getLogger("risk.news_filter")


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

class NewsImpact(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    FOMC   = "FOMC"      # central-bank decision — always blocks


@dataclass(frozen=True)
class NewsEvent:
    """
    FIX #1: Scheduled economic news event.

    Fields
    ------
    title      : human-readable description, e.g. "NFP"
    currency   : ISO-4217 currency code affected, e.g. "USD", or "ALL"
    impact     : one of NewsImpact / free string from provider
    event_time : tz-aware datetime; naive → assumed UTC
    """
    title:      str
    currency:   str
    impact:     str
    event_time: datetime

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            object.__setattr__(
                self, "event_time",
                self.event_time.replace(tzinfo=timezone.utc),
            )


@dataclass(frozen=True)
class NewsBlockResult:
    """Returned when a news gate fires."""
    blocked:          bool
    reason:           str
    event_title:      str        = ""
    event_currency:   str        = ""
    event_impact:     str        = ""
    event_time:       Optional[datetime] = None
    minutes_to_event: float      = 0.0


# ---------------------------------------------------------------------------
# Provider protocol (optional)
# ---------------------------------------------------------------------------

class NewsProvider(Protocol):
    """Any object with an async `fetch(date: datetime) -> List[NewsEvent]`."""
    async def fetch(self, for_date: datetime) -> List[NewsEvent]: ...


# ---------------------------------------------------------------------------
# Core gate
# ---------------------------------------------------------------------------

class NewsFilterGate:
    """
    FIX #1: Real news-event gate.

    Usage
    -----
    gate = NewsFilterGate(block_minutes_before=30, block_minutes_after=15)
    gate.load_events(events)               # manual injection
    result = gate.check(symbol, now)       # synchronous — no I/O
    await gate.refresh_from_provider(now)  # optional live refresh
    """

    def __init__(
        self,
        block_minutes_before: int = 30,
        block_minutes_after:  int = 15,
        min_impact:           str = NewsImpact.HIGH,
        provider: Optional[NewsProvider] = None,
        refresh_interval_s:   int = 3600,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._before_s = block_minutes_before * 60
        self._after_s  = block_minutes_after  * 60
        self._min_impact   = min_impact
        self._provider     = provider
        self._refresh_s    = refresh_interval_s
        self._clock        = clock or (lambda: datetime.now(timezone.utc))

        self._events: List[NewsEvent] = []
        self._lock   = asyncio.Lock()
        self._last_refresh: Optional[datetime] = None

        self._impact_rank: Dict[str, int] = {
            NewsImpact.LOW:    1,
            NewsImpact.MEDIUM: 2,
            NewsImpact.HIGH:   3,
            NewsImpact.FOMC:   4,
        }

    def load_events(self, events: List[NewsEvent]) -> None:
        valid = []
        for ev in events:
            if not isinstance(ev, NewsEvent):
                logger.warning("NewsFilterGate.load_events: skipping non-NewsEvent %r", ev)
                continue
            valid.append(ev)
        self._events = valid
        logger.info(
            "NewsFilterGate: loaded %d events (before=%ds after=%ds min_impact=%s)",
            len(valid), self._before_s, self._after_s, self._min_impact,
        )

    def add_event(self, event: NewsEvent) -> None:
        self._events.append(event)

    def clear_events(self) -> None:
        self._events.clear()

    def event_count(self) -> int:
        return len(self._events)

    def check(
        self,
        symbol:  str,
        now:     Optional[datetime] = None,
    ) -> NewsBlockResult:
        """
        FIX #1: Check all loaded events against [now - before, now + after].
        Fail-safe: any internal exception → log + return NOT blocked.
        """
        if not self._events:
            return NewsBlockResult(blocked=False, reason="NO_EVENTS_LOADED")
        try:
            return self._check_inner(symbol, now or self._clock())
        except Exception as exc:
            logger.warning(
                "NewsFilterGate.check() exception for %s: %s — continuing normally",
                symbol, exc, exc_info=False,
            )
            return NewsBlockResult(blocked=False, reason=f"PROVIDER_FAIL_SAFE:{exc}")

    def _check_inner(self, symbol: str, now: datetime) -> NewsBlockResult:
        sym_currencies = self._currencies_for(symbol)
        min_rank = self._impact_rank.get(self._min_impact, 3)

        for ev in self._events:
            ev_ccy = ev.currency.upper().strip()
            if ev_ccy != "ALL" and ev_ccy not in sym_currencies:
                continue
            ev_rank = self._impact_rank.get(ev.impact.upper(), 3)
            if ev_rank < min_rank:
                continue
            diff_s = (now - ev.event_time).total_seconds()
            if -self._before_s <= diff_s <= self._after_s:
                minutes_to = -diff_s / 60
                reason = (
                    f"NEWS_EVENT_BLOCK: '{ev.title}' ({ev_ccy} {ev.impact}) "
                    f"@ {ev.event_time.isoformat()} "
                    f"[window: -{self._before_s//60}m/+{self._after_s//60}m]"
                )
                logger.warning(
                    "NewsFilterGate BLOCKED %s — %s (%.1f min to event)",
                    symbol, reason, minutes_to,
                )
                return NewsBlockResult(
                    blocked=True,
                    reason="NEWS_EVENT_BLOCK",
                    event_title=ev.title,
                    event_currency=ev_ccy,
                    event_impact=ev.impact,
                    event_time=ev.event_time,
                    minutes_to_event=round(minutes_to, 1),
                )

        return NewsBlockResult(blocked=False, reason="CLEAR")

    async def refresh_from_provider(
        self,
        now: Optional[datetime] = None,
        force: bool = False,
    ) -> bool:
        """
        FIX #1.5: Fetch from optional live provider.
        Fail-safe: provider failure → log warning, keep old events.
        """
        if self._provider is None:
            return False
        if not force:
            if self._last_refresh is not None:
                elapsed = ((now or self._clock()) - self._last_refresh).total_seconds()
                if elapsed < self._refresh_s:
                    return False
        async with self._lock:
            try:
                fetch_date = now or self._clock()
                events = await asyncio.wait_for(
                    self._provider.fetch(fetch_date),
                    timeout=10.0,
                )
                self.load_events(events)
                self._last_refresh = fetch_date
                logger.info("NewsFilterGate: refreshed %d events from provider", len(events))
                return True
            except asyncio.TimeoutError:
                logger.warning("NewsFilterGate: provider timeout — keeping %d existing events", len(self._events))
            except Exception as exc:
                logger.warning("NewsFilterGate: provider error (%s) — keeping %d existing events", exc, len(self._events))
        return False

    @staticmethod
    def _currencies_for(symbol: str) -> set:
        sym = symbol.upper().strip()
        if len(sym) == 6 and sym.isalpha():
            return {sym[:3], sym[3:]}
        if len(sym) > 3 and sym.isalpha():
            return {sym[:3]}
        return {sym}

    def upcoming_events(
        self,
        symbol: str,
        lookahead_minutes: int = 120,
        now: Optional[datetime] = None,
    ) -> List[NewsEvent]:
        """Return events that will block this symbol within the next N minutes."""
        n = now or self._clock()
        cutoff = n + timedelta(minutes=lookahead_minutes)
        sym_currencies = self._currencies_for(symbol)
        result = []
        for ev in self._events:
            if ev.currency.upper() != "ALL" and ev.currency.upper() not in sym_currencies:
                continue
            if n <= ev.event_time <= cutoff:
                result.append(ev)
        return sorted(result, key=lambda e: e.event_time)
