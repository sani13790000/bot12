"""\nbackend/risk/news_filter.py\n============================================
Fixes:
  - LOG-FIX-3: cap _events list at 500 with eviction in add_event()\n"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("risk.news_filter")

_MAX_EVENTS: int = 500  # LOG-FIX-3: cap on calendar events to prevent memory growth


class NewsImpact:
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    FOMC   = "fomc"


@dataclass(frozen=True)
class NewsEvent:
    currency:   str
    impact:     str
    time_utc:   datetime
    title:      str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", self.currency.upper())


@dataclass
class NewsBlockResult:
    blocked:    bool
    reason:     str = ""
    events:     List[NewsEvent] = None

    def __post_init__(self) -> None:
        if self.events is None:
            object.__setattr__(self, "events", [])


class NewsFilterGate:
    """Blocks trades during high-impact news windows."""

    def __init__(
        self,
        before_secs:        int = 600,
        after_secs:         int = 300,
        min_impact:         str = NewsImpact.HIGH,
        refresh_interval_s: int = 3600,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._before_s      = before_secs
        self._after_s       = after_secs
        self._min_impact    = min_impact
        self._refresh_s     = refresh_interval_s
        self._clock         = clock or (lambda: datetime.now(timezone.utc))

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
        valid = [ev for ev in events if isinstance(ev, NewsEvent)]
        if len(valid) > _MAX_EVENTS:
            logger.warning("NewsFilter: truncating %d events to %d", len(valid), _MAX_EVENTS)
            valid = valid[-_MAX_EVENTS:]
        self._events = valid
        logger.info(
            "NewsFilterGate: loaded %d events (before=%ds after=%ds min_impact=%s)",
            len(valid), self._before_s, self._after_s, self._min_impact,
        )

    def add_event(self, event: NewsEvent) -> None:
        if len(self._events) >= _MAX_EVENTS:  # LOG-FIX-3: prevent unbounded growth
            logger.warning("NewsFilterGate.add_event: max events reached (%d), dropping oldest", _MAX_EVENTS)
            self._events = self._events[-(_MAX_EVENTS - 1):]
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
        now = now or  self._clock()
        syms = {symbol[:3].upper(), symbol[3:].upper()}
        min_rank = self._impact_rank.get(self._min_impact, 0)
        blocking = []
        for ev in self._events:
            if ev.currency not in syms:
                continue
            if self._impact_rank.get(ev.impact, 0) < min_rank:
                continue
            secs = (now - ev.time_utc).total_seconds()
            if -self._before_s <= secs <= self._after_s:
                blocking.append(ev)
        if blocking:
            return NewsBlockResult(
                blocked=True,
                reason=f"News window: {[', '.join(set(e.title for e in blocking))]}",
                events=blocking,
            )
        return NewsBlockResult(blocked=False)

    async def refresh_if_needed(
        self,
        provider: Callable[[], List[NewsEvent]],
    ) -> None:
        now = self._clock()
        if self._last_refresh and (now - self._last_refresh).total_seconds() < self._refresh_s:
            return
        try:
            events = await provider()
            self.load_events(events)
            self._last_refresh = now
        except asyncio.TimeoutError:
            logger.warning("NewsFilterGate: provider timeout — keeping %d existing events", len(self._events))
        except Exception as exc:
            logger.warning("NewsFilterGate: provider error (%s) - keeping %d existing events", exc, len(self._events))

    def snapshot(self) -> Dict:
        now = self._clock()
        upcoming = [
            {"currency": e.currency, "title": e.title, "impact": e.impact,
             "time_utc": e.time_utc.isoformat(),
             "secs_until": round((e.time_utc - now).total_seconds())}
            for e in self._events
            if (e.time_utc - now).total_seconds() > 0
        ]
        return {
            "total_events": len(self._events),
            "upcoming_1h":  sum(1 for e in upcoming if e["secs_until"] < 3600),
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "min_impact":   self._min_impact,
            "max_events":   _MAX_EVENTS,
        }
