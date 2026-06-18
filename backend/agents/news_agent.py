from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base_agent import AgentVote, AgentStatus, BaseAgent

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class _NewsCache:
    TTL_SECONDS: int = 15 * 60

    def __init__(self) -> None:
        self._data: List[Dict] = []
        self._fetched_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    def is_fresh(self) -> bool:
        if self._fetched_at is None:
            return False
        age = (datetime.now(timezone.utc) - self._fetched_at).total_seconds()
        return age < self.TTL_SECONDS

    def get(self) -> List[Dict]:
        return list(self._data)

    def set(self, data: List[Dict]) -> None:
        self._data = data
        self._fetched_at = datetime.now(timezone.utc)


_NEWS_CACHE = _NewsCache()


async def _fetch_news_events(timeout: float = 5.0) -> List[Dict]:
    if not _HTTPX_AVAILABLE:
        return []

    base_url = os.getenv(
        "ECONOMIC_CALENDAR_URL",
        "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
    )
    api_key = os.getenv("FOREX_FACTORY_KEY", "")
    now = datetime.now(timezone.utc)
    results: List[Dict] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            resp = await client.get(base_url, headers=headers)
            resp.raise_for_status()
            raw_events = resp.json()

            for ev in raw_events:
                impact = str(ev.get("impact", ev.get("impactTitle", "LOW"))).upper()
                if impact not in ("HIGH", "MEDIUM"):
                    continue

                date_str = ev.get("date", ev.get("dateUtc", ""))
                time_str = ev.get("time", "12:00am")
                try:
                    event_dt = datetime.strptime(
                        f"{date_str} {time_str}", "%b %d, %Y %I:%M%p"
                    ).replace(tzinfo=timezone.utc)
                except Exception:
                    try:
                        event_dt = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        continue

                delta_min = (event_dt - now).total_seconds() / 60.0
                results.append({
                    "name": str(ev.get("title", ev.get("name", "Unknown"))).upper(),
                    "impact": impact,
                    "minutes_to_event":    max(0.0, delta_min) if delta_min > 0 else 999.0,
                    "minutes_since_event": max(0.0, -delta_min) if delta_min < 0 else 999.0,
                })

    except Exception:
        return []

    return results


class NewsAgent(BaseAgent):
    HIGH_IMPACT_EVENTS = {"NFP", "FOMC", "CPI", "GDP", "RATE_DECISION", "PMI", "UNEMPLOYMENT"}

    def __init__(
        self,
        weight: float = 0.10,
        enabled: bool = True,
        block_on_high_impact: bool = False,
        minutes_before: int = 30,
        minutes_after: int = 15,
    ) -> None:
        super().__init__(name="News", weight=weight, enabled=enabled)
        self.block_on_high_impact = block_on_high_impact
        self.minutes_before = minutes_before
        self.minutes_after  = minutes_after

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        if not context.get("news_filter_enabled", True):
            return AgentVote(
                score=80.0, confidence=60.0,
                direction=context.get("direction", "NEUTRAL"),
                status=AgentStatus.OK,
                reason="News filter disabled",
                metadata={"filter_active": False},
            )

        score      = 90.0
        confidence = 70.0
        reasons: List[str] = []
        blocked    = False

        upcoming_news: List[Dict] = context.get("upcoming_news", [])
        fetched_from_api = False

        if not upcoming_news:
            async with _NEWS_CACHE._lock:
                if not _NEWS_CACHE.is_fresh():
                    fetched = await _fetch_news_events(timeout=4.0)
                    if fetched:
                        _NEWS_CACHE.set(fetched)
                upcoming_news = _NEWS_CACHE.get()
            fetched_from_api = True

        for event in upcoming_news:
            impact        = str(event.get("impact", "LOW")).upper()
            event_name    = str(event.get("name", ""))
            minutes_to    = float(event.get("minutes_to_event", 999))
            minutes_since = float(event.get("minutes_since_event", 999))

            if impact == "HIGH" or event_name.upper() in self.HIGH_IMPACT_EVENTS:
                if minutes_to <= self.minutes_before:
                    score -= 40.0
                    reasons.append(f"High impact event in {minutes_to:.0f}min: {event_name}")
                    if self.block_on_high_impact and minutes_to <= 15:
                        blocked = True
                        score   = 0.0
                        reasons.append(f"BLOCKED: {event_name} < 15min away")
                elif minutes_since <= self.minutes_after:
                    score -= 25.0
                    reasons.append(f"Post-event cooldown ({minutes_since:.0f}min): {event_name}")
            elif impact == "MEDIUM":
                if minutes_to <= 15:
                    score -= 10.0
                    reasons.append(f"Medium event soon: {event_name}")

        if not upcoming_news:
            score = 90.0
            reasons.append("No significant news nearby")

        score      = max(0.0, min(100.0, score))
        confidence = max(0.0, min(100.0, confidence))
        status     = AgentStatus.ERROR if blocked else AgentStatus.OK

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=status,
            reason=" | ".join(reasons) if reasons else "News clear",
            metadata={
                "blocked": blocked,
                "events_count": len(upcoming_news),
                "block_on_high_impact": self.block_on_high_impact,
                "fetched_from_api": fetched_from_api,
                "httpx_available": _HTTPX_AVAILABLE,
            },
        )
