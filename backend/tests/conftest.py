"""conftest.py --- Global pytest fixtures for Galaxy Vast AI Trading Platform."""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "live: mark test as requiring live MT5 gateway")
    config.addinivalue_line("markers", "db: mark test as requiring live Supabase")


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── MT5 Connector mock ────────────────────────────────────────────────────── #
@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.connected = True
    broker.demo = True
    broker.connect = AsyncMock(return_value=True)
    broker.disconnect = AsyncMock(return_value=True)
    broker.place_order = AsyncMock(return_value={"ticket": 999001, "price": 1.1050})
    broker.close_position = AsyncMock(return_value=True)
    broker.get_open_positions = AsyncMock(return_value=[])
    broker.get_account_info = AsyncMock(
        return_value={
            "balance": 10_000.0,
            "equity": 10_050.0,
            "margin": 200.0,
            "free_margin": 9_850.0,
            "profit": 50.0,
            "leverage": 100,
        }
    )
    broker.get_candles = AsyncMock(
        return_value=[
            {
                "time": 1_700_000_000 + i * 3600,
                "open": 1.1000 + i * 0.0001,
                "high": 1.1010 + i * 0.0001,
                "low": 1.0990 + i * 0.0001,
                "close": 1.1005 + i * 0.0001,
                "tick_volume": 500 + i,
            }
            for i in range(200)
        ]
    )
    broker.health_check = AsyncMock(return_value={"status": "ok", "latency_ms": 12.3})
    return broker


# ── OrderStateMachine mock ────────────────────────────────────────────────── #
@pytest.fixture
def mock_osm():
    """
    Mock که API واقعی OSM را منعکس می‌کند:
    - register(ticket) نه create()
    - transition(ticket, new_state)
    - get_state(ticket)
    - is_terminal(ticket)
    - active_tickets
    """
    osm = MagicMock()
    _states: Dict[int, str] = {}

    def _register(ticket: int) -> None:
        _states[ticket] = "PENDING"

    def _transition(ticket: int, new_state: str) -> None:
        _states[ticket] = new_state

    def _get_state(ticket: int):
        return _states.get(ticket)

    def _is_terminal(ticket: int) -> bool:
        return _states.get(ticket) in {"CLOSED", "REJECTED", "CANCELLED", "ERROR"}

    osm.register = MagicMock(side_effect=_register)
    osm.transition = MagicMock(side_effect=_transition)
    osm.get_state = MagicMock(side_effect=_get_state)
    osm.is_terminal = MagicMock(side_effect=_is_terminal)
    osm.active_tickets = property(lambda self: list(_states.keys()))
    osm.stats = MagicMock(return_value={"total": len(_states), "active": 0})
    return osm


# ── Risk mock ─────────────────────────────────────────────────────────────── #
@pytest.fixture
def mock_risk():
    risk = MagicMock()
    risk.is_kill_switch_active = MagicMock(return_value=False)
    risk.check_risk = MagicMock(return_value={"allowed": True, "reason": "ok"})
    risk.calculate_lot = MagicMock(return_value=0.10)
    return risk


# ── Base signal dict ──────────────────────────────────────────────────────── #
@pytest.fixture
def base_signal() -> Dict[str, Any]:
    return {
        "symbol": "EURUSD",
        "direction": "BUY",
        "entry": 1.1050,
        "sl": 1.1000,
        "tp": 1.1150,
        "confidence": 0.82,
        "lot": 0.10,
        "timeframe": "H1",
        "source": "pytest",
    }


# ── DB mock ───────────────────────────────────────────────────────────────── #
@pytest.fixture
def mock_db():
    db = MagicMock()
    db.ping = AsyncMock(return_value=True)
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock(return_value={"id": "mock-uuid-001"})
    db.update = AsyncMock(return_value={"id": "mock-uuid-001"})
    db.delete = AsyncMock(return_value=True)
    return db


# ── VotingEngine mock ─────────────────────────────────────────────────────── #
@pytest.fixture
def mock_voting():
    ve = MagicMock()
    ve.vote = AsyncMock(
        return_value=MagicMock(
            approved=True,
            confidence=0.82,
            votes=[],
            to_dict=lambda: {"approved": True, "confidence": 0.82},
        )
    )
    return ve
