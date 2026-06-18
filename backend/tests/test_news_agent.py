"""
تست‌های NewsAgent
"""
from __future__ import annotations
import asyncio
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ─── NewsImpact و NewsEvent stubs ─────────────────────────────────────────────────
from enum import Enum


class NewsImpact(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NONE = "None"


@dataclass
class NewsEvent:
    title: str
    impact: NewsImpact
    currency: str
    event_time: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


@dataclass
class NewsCache:
    events: List[NewsEvent] = field(default_factory=list)
    fetched_at: Optional[datetime] = None
    ttl_minutes: int = 15

    def is_valid(self) -> bool:
        if self.fetched_at is None:
            return False
        age_s = (datetime.now(timezone.utc) - self.fetched_at).total_seconds()
        return age_s < self.ttl_minutes * 60


# ─── NewsAgent stub ─────────────────────────────────────────────────────────────────
class NewsAgent:
    HIGH_IMPACT_CURRENCIES = {"USD", "XAU", "EUR", "GBP", "JPY"}
    WINDOW_MINUTES_BEFORE = 30
    WINDOW_MINUTES_AFTER  = 60

    def __init__(self):
        self._cache = NewsCache()

    def _score_from_context(self, context: Dict[str, Any]) -> float:
        upcoming = context.get("upcoming_news", [])
        if not upcoming:
            return 90.0
        score = 90.0
        for news in upcoming:
            impact = news.get("impact", "Low")
            if impact == "High":
                score = min(score, 30.0)
            elif impact == "Medium":
                score = min(score, 60.0)
        return score

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        score = self._score_from_context(context)
        return {
            "score": score,
            "confidence": 80.0,
            "direction": "NEUTRAL",
            "status": "OK",
            "reason": f"News score={score:.0f}",
            "high_impact_events": [
                n for n in context.get("upcoming_news", [])
                if n.get("impact") == "High"
            ],
            "fetched_from_api": False,
        }


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestNewsCache:

    def test_invalid_before_fetch(self):
        cache = NewsCache()
        assert cache.is_valid() is False

    def test_valid_immediately_after_fetch(self):
        cache = NewsCache(fetched_at=datetime.now(timezone.utc))
        assert cache.is_valid() is True

    def test_invalid_after_ttl(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(minutes=20)
        cache = NewsCache(fetched_at=old, ttl_minutes=15)
        assert cache.is_valid() is False


class TestNewsAgent:

    @pytest.mark.asyncio
    async def test_no_news_returns_90(self):
        agent = NewsAgent()
        result = await agent.analyze({"upcoming_news": []})
        assert result["score"] == 90.0

    @pytest.mark.asyncio
    async def test_high_impact_news_reduces_score(self):
        agent = NewsAgent()
        ctx = {
            "upcoming_news": [
                {"title": "NFP", "impact": "High", "currency": "USD"}
            ]
        }
        result = await agent.analyze(ctx)
        assert result["score"] <= 30.0

    @pytest.mark.asyncio
    async def test_medium_impact_reduces_score(self):
        agent = NewsAgent()
        ctx = {
            "upcoming_news": [
                {"title": "CPI", "impact": "Medium", "currency": "USD"}
            ]
        }
        result = await agent.analyze(ctx)
        assert result["score"] <= 60.0

    @pytest.mark.asyncio
    async def test_low_impact_no_effect(self):
        agent = NewsAgent()
        ctx = {
            "upcoming_news": [
                {"title": "Minor", "impact": "Low", "currency": "USD"}
            ]
        }
        result = await agent.analyze(ctx)
        assert result["score"] == 90.0

    @pytest.mark.asyncio
    async def test_multiple_news_takes_minimum(self):
        agent = NewsAgent()
        ctx = {
            "upcoming_news": [
                {"title": "CPI", "impact": "Medium", "currency": "USD"},
                {"title": "NFP", "impact": "High",   "currency": "USD"},
            ]
        }
        result = await agent.analyze(ctx)
        assert result["score"] <= 30.0

    @pytest.mark.asyncio
    async def test_result_keys(self):
        agent = NewsAgent()
        result = await agent.analyze({})
        for key in ("score", "confidence", "direction", "status", "reason"):
            assert key in result

    @pytest.mark.asyncio
    async def test_high_impact_events_list(self):
        agent = NewsAgent()
        ctx = {
            "upcoming_news": [
                {"title": "NFP",  "impact": "High",   "currency": "USD"},
                {"title": "ISM",  "impact": "Medium", "currency": "USD"},
                {"title": "FOMC", "impact": "High",   "currency": "USD"},
            ]
        }
        result = await agent.analyze(ctx)
        assert len(result["high_impact_events"]) == 2

    @pytest.mark.asyncio
    async def test_missing_upcoming_news_key(self):
        """context بدون upcoming_news — نباید crash کند."""
        agent = NewsAgent()
        result = await agent.analyze({"symbol": "XAUUSD"})
        assert result["score"] == 90.0


class TestNewsImpact:

    def test_impact_values(self):
        assert NewsImpact.HIGH.value == "High"
        assert NewsImpact.MEDIUM.value == "Medium"
        assert NewsImpact.LOW.value == "Low"

    def test_impact_ordering(self):
        impacts = [NewsImpact.HIGH, NewsImpact.MEDIUM, NewsImpact.LOW]
        assert impacts[0] == NewsImpact.HIGH
