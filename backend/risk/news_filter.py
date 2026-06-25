"""backend/risk/news_filter.py
===================================================
Fixes:
  - LOG-FIX-3: cap _events list at 500 with eviction in add_event()
  - STRESS-3: ContextualLogger.info/warning called with %s positional args
              but ContextualLogger only accepts msg + **kwargs (keyword-only).
              All logger calls converted to keyword-arg style.
"""
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
    currency:  str
    impact:    str
    time_utc:  datetime
    title:     str = ""

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
            # STRESS-3: use keyword args instead of positional %s
            logger.warning(
                "NewsFilter: truncating events to max",
                original=len(valid),
                max_events=_MAX_EVENTS,
            )
            valid = valid[-_MAX_EVENTS:]
        self._events = valid
        logger.info(
            "NewsFilterGate: events loaded",
            count=len(valid),
            before_s=self._before_s,
            after_s=self._after_s,
            min_impact=self._min_impact,
        )

    def add_event(self, event: NewsEvent) -> None:
        if len(self._events) >= _MAX_EVENTS:  # LOG-FIX-3: prevent unbounded growth
            logger.warning(
                "NewsFilterGate.add_event: max events reached, dropping oldest",
                max_events=_MAX_EVENTS,
            )
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
        if now is None:
            now = self._clock()

        sym_upper = symbol[:6].upper()
        min_rank  = self._impact_rank.get(self._min_impact, 3)
        triggered: List[NewsEvent] = []

        for event in self._events:
            # Currency filter: EUR in EURUSD, USD in EURUSD
            event_ccy = event.currency.upper()
            if event_ccy not in sym_upper and event_ccy not in ("USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"):
                continue
            if sym_upper[:3] != event_ccy and sym_upper[3:] != event_ccy:
                continue

            # Impact filter
            if self._impact_rank.get(event.impact.lower(), 0) < min_rank:
                continue

            # Time window check
            try:
                ev_time = event.time_utc
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                delta_s = (ev_time - now).total_seconds()
                # Block if within window: -after_s <= delta_s <= before_s
                if -self._after_s <= delta_s <= self._before_s:
                    triggered.append(event)
            except Exception as exc:
                logger.debug("news_filter time parse error", error=str(exc))
                continue

        if triggered:
            first = triggered[0]
            ev_time = first.time_utc
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)
            delta_s = (ev_time - now).total_seconds()
            return NewsBlockResult(
                blocked=True,
                reason=f"News blackout: {first.currency} {first.title} in {delta_s/60:.1f}min",
                events=triggered,
            )

        return NewsBlockResult(blocked=False)

    async def refresh_if_needed(self, provider) -> None:
        now = self._clock()
        if (self._last_refresh is None or
                (now - self._last_refresh).total_seconds() > self._refresh_s):
            try:
                events = await provider.fetch()
                self.load_events(events)
                self._last_refresh = now
            except Exception as exc:
                logger.warning("news_filter refresh failed", error=str(exc))

    def snapshot(self) -> Dict:
        return {
            "event_count": len(self._events),
            "before_s":    self._before_s,
            "after_s":     self._after_s,
            "min_impact":  self._min_impact,
        }
