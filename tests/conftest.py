"""
conftest.py — shared fixtures for all bot12 tests.
All fixtures use DEMO mode — no real MT5 connection required.
"""
from __future__ import annotations

import asyncio
import os
import pytest

# Force DEMO mode for all tests
os.environ.setdefault("MT5_DEMO_MODE", "true")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test")
os.environ.setdefault("TELEGRAM_ADMIN_IDS", "[123456789]")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("MT5_GATEWAY_URL", "http://localhost:9000")


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def demo_mt5_connector():
    """MT5Connector in DEMO mode — no real gateway needed."""
    from backend.execution.mt5_connector import MT5Connector
    connector = MT5Connector(demo=True)
    return connector


@pytest.fixture(scope="session")
def kill_switch_instance():
    """Fresh KillSwitch instance for tests."""
    from backend.risk.kill_switch import KillSwitch, KillSwitchConfig
    cfg = KillSwitchConfig(
        max_daily_loss_pct=5.0,
        max_drawdown_pct=10.0,
        max_consecutive_losses=5,
    )
    return KillSwitch(config=cfg)


@pytest.fixture(scope="session")
def smc_agent_instance():
    from backend.agents.smc_agent import SMCAgent
    return SMCAgent()


@pytest.fixture(scope="session")
def news_agent_instance():
    from backend.agents.news_agent import NewsAgent
    return NewsAgent()


@pytest.fixture(scope="session")
def ml_agent_instance():
    from backend.agents.ml_agent import MLAgent
    return MLAgent()


@pytest.fixture(scope="session")
def voting_engine_instance():
    from backend.agents.voting_engine import VotingEngine
    return VotingEngine()


@pytest.fixture(scope="session")
def signal_processor_instance(smc_agent_instance, ml_agent_instance, news_agent_instance):
    from backend.services.signal_processor import SignalProcessor
    sp = SignalProcessor()
    sp.register_agents([smc_agent_instance, ml_agent_instance, news_agent_instance])
    return sp


@pytest.fixture
def sample_candles():
    """Minimal OHLCV candle list for SMC/PA testing."""
    import random
    random.seed(42)
    candles = []
    price = 1.1000
    for i in range(50):
        o = price
        h = price + random.uniform(0.0005, 0.002)
        l = price - random.uniform(0.0005, 0.002)
        c = random.uniform(l, h)
        candles.append({"open": o, "high": h, "low": l, "close": c, "volume": random.randint(100, 1000)})
        price = c
    return candles


@pytest.fixture
def sample_risk_input():
    """Standard RiskInput for risk pipeline tests."""
    try:
        from backend.risk.risk_orchestrator import RiskInput
        return RiskInput(
            symbol="EURUSD",
            direction="BUY",
            volume=0.01,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
            equity=10000.0,
            balance=10000.0,
            free_margin=8000.0,
            used_margin=2000.0,
        )
    except Exception:
        return None
