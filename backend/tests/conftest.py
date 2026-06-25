"""conftest.py — Global pytest fixtures for Galaxy Vast AI Trading Platform."""
from __future__ import annotations
import asyncio, sys, os
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ── isolate from real backend imports ─────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ── asyncio mode ──────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast, no I/O")
    config.addinivalue_line("markers", "integration: cross-module")
    config.addinivalue_line("markers", "e2e: full pipeline")
    config.addinivalue_line("markers", "security: security tests")
    config.addinivalue_line("markers", "load: load tests")

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()

@pytest.fixture
def mock_broker():
    b = AsyncMock()
    b.initialize.return_value = True
    b.shutdown.return_value = None
    b.health_check.return_value = True
    b.send_order.return_value = MagicMock(retcode=10009, order=12345, volume=0.01, price=1.1000, comment="ok")
    b.get_positions.return_value = []
    b.close_position.return_value = True
    return b

@pytest.fixture
def mock_osm():
    osm = AsyncMock()
    order = MagicMock()
    order.order_id = "test-order-001"
    order.symbol = "EURUSD"
    order.direction = "BUY"
    order.lot_size = 0.01
    order.entry_price = 1.1000
    order.stop_loss = 1.0950
    order.take_profit = 1.1100
    osm.create_order.return_value = order
    osm.start.return_value = None
    osm.transition.return_value = True
    return osm

@pytest.fixture
def mock_failure_recovery():
    fr = AsyncMock()
    fr.start.return_value = None
    fr.stop.return_value = None
    fr.handle_failure.return_value = None
    fr.set_retry_callback = MagicMock()
    return fr

@pytest.fixture
def mock_reconciliation():
    pr = AsyncMock()
    pr.start.return_value = None
    pr.stop.return_value = None
    pr.run_once.return_value = MagicMock(orphans=[], mismatches=[])
    pr.set_mt5 = MagicMock()
    return pr

@pytest.fixture
def mock_risk():
    r = AsyncMock()
    result = MagicMock()
    result.approved = True
    result.decision = MagicMock(value="APPROVED")
    result.block_reason = None
    result.risk_percent = 1.0
    result.lot_size = 0.01
    result.lot_multiplier = 1.0
    result.gates_passed = ["vol", "corr", "exposure"]
    result.gates_failed = []
    result.metadata = {}
    result.to_dict.return_value = {
        "approved": True, "decision": "APPROVED",
        "block_reason": None, "risk_percent": 1.0,
        "lot_size": 0.01, "lot_multiplier": 1.0,
        "gates_passed": ["vol","corr","exposure"],
        "gates_failed": [], "metadata": {}
    }
    r.assess.return_value = result
    r.check.return_value = result
    return r

@pytest.fixture
def base_signal() -> Dict[str, Any]:
    return {
        "signal_id": "sig-001",
        "symbol": "EURUSD",
        "direction": "BUY",
        "balance": 10000.0,
        "equity": 10000.0,
        "entry_price": 1.10000,
        "stop_loss": 1.09500,
        "take_profit": 1.11000,
        "stop_loss_pips": 50.0,
        "current_atr": 15.0,
        "atr_history": [12.0, 13.0, 14.0, 15.0, 16.0],
        "current_spread": 1.5,
        "avg_spread": 1.2,
        "open_positions": [],
        "today_trades_count": 0,
        "today_pnl_usd": 0.0,
        "week_pnl_usd": 0.0,
        "month_pnl_usd": 0.0,
        "win_rate": 0.55,
        "avg_rr": 1.5,
        "user_id": "user-001",
    }
