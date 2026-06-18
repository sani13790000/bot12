"""
Galaxy Vast AI Trading Platform
pytest conftest — shared fixtures
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class AgentStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass
class _AgentVote:
    score: float
    confidence: float
    direction: str
    status: AgentStatus
    reason: str


@dataclass
class _AgentResult:
    agent_name: str
    vote: _AgentVote
    elapsed_ms: float = 0.0
    error: str = ""


@pytest.fixture
def make_vote():
    def _make(score=70.0, confidence=80.0, direction="BUY",
              status="OK", reason="test ok"):
        return _AgentVote(
            score=score,
            confidence=confidence,
            direction=direction,
            status=AgentStatus(status),
            reason=reason,
        )
    return _make


@pytest.fixture
def make_agent(make_vote):
    """Factory: stub BaseAgent."""
    def _make(name="agent", weight=0.5, score=70.0,
              direction="BUY", status="OK", enabled=True):
        agent = MagicMock()
        agent.name = name
        agent.weight = weight
        agent.enabled = enabled
        vote = make_vote(score=score, direction=direction, status=status)

        async def run(ctx):
            return _AgentResult(agent_name=name, vote=vote, elapsed_ms=1.0)

        agent.run = run
        return agent
    return _make


@pytest.fixture
def market_context():
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "close": [1900.0 + i * 0.5 for i in range(100)],
        "high":  [1901.0 + i * 0.5 for i in range(100)],
        "low":   [1899.0 + i * 0.5 for i in range(100)],
        "open":  [1900.0 + i * 0.4 for i in range(100)],
        "volume": [1000 + i * 10 for i in range(100)],
        "bid": 1950.0,
        "ask": 1950.5,
        "spread": 0.5,
        "atr": 5.0,
        "session": "LONDON",
        "upcoming_news": [],
        "balance": 10000.0,
        "equity": 10000.0,
    }


@pytest.fixture
def sample_candles():
    candles = []
    price = 1900.0
    for i in range(200):
        price += 0.5 if i % 3 != 0 else -0.3
        candles.append({
            "time": f"2024-01-{(i // 24) + 1:02d}T{(i % 24):02d}:00:00",
            "open":  round(price - 0.2, 2),
            "high":  round(price + 0.8, 2),
            "low":   round(price - 0.8, 2),
            "close": round(price, 2),
            "volume": 1000 + i,
        })
    return candles


@pytest.fixture
def ml_features():
    return {
        "rsi": 55.0,
        "macd": 0.5,
        "atr": 5.0,
        "bb_upper": 1960.0,
        "bb_lower": 1940.0,
        "ema_20": 1950.0,
        "ema_50": 1948.0,
        "volume_ratio": 1.2,
        "session_london": 1.0,
        "session_new_york": 0.0,
        "hour_of_day": 10.0,
        "day_of_week": 2.0,
    }
