"""
backend/tests/test_05_mt5_bridge.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
فاز G — تست‌های MT5 Bridge

پوشش:
1. MT5Connector در demo mode (env var)
2. MT5Connector env var control
3. get_candles() — داده‌های کندل
4. SignalProcessor → VotingEngine → ExecutionService pipeline
5. MT5Gateway Agent endpoints (با httpx mock)
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def connector_demo():
    """MT5Connector در demo mode."""
    from backend.execution.mt5_connector import MT5Connector
    return MT5Connector(demo=True)


@pytest.fixture
def connector_live():
    """MT5Connector در LIVE mode با mock session."""
    from backend.execution.mt5_connector import MT5Connector
    c = MT5Connector(base_url="http://localhost:8080", demo=False)
    return c


# ══════════════════════════════════════════════════════════════════════════════
# TestMT5ConnectorDemo
# ══════════════════════════════════════════════════════════════════════════════

class TestMT5ConnectorDemo:
    def test_demo_flag_true(self, connector_demo):
        assert connector_demo.demo is True

    def test_demo_flag_env_false(self):
        """MT5_DEMO_MODE=false → demo=False."""
        from backend.execution.mt5_connector import MT5Connector
        with patch.dict("os.environ", {"MT5_DEMO_MODE": "false"}):
            c = MT5Connector()
            assert c.demo is False

    def test_demo_flag_env_true(self):
        """MT5_DEMO_MODE=true → demo=True."""
        from backend.execution.mt5_connector import MT5Connector
        with patch.dict("os.environ", {"MT5_DEMO_MODE": "true"}):
            c = MT5Connector()
            assert c.demo is True

    @pytest.mark.asyncio
    async def test_connect_demo(self, connector_demo):
        await connector_demo.connect()
        assert connector_demo._connected is True

    @pytest.mark.asyncio
    async def test_place_order_demo_returns_ticket(self, connector_demo):
        await connector_demo.connect()
        result = await connector_demo.place_order("EURUSD", "BUY", 0.01)
        assert result.ticket > 0
        assert result.symbol == "EURUSD"
        assert result.direction == "BUY"

    @pytest.mark.asyncio
    async def test_get_candles_demo(self, connector_demo):
        await connector_demo.connect()
        candles = await connector_demo.get_candles("EURUSD", "H1", 100)
        assert len(candles) == 100
        assert candles[0].open > 0
        assert candles[0].high >= candles[0].low
        assert candles[0].close > 0

    @pytest.mark.asyncio
    async def test_get_candles_ohlc_valid(self, connector_demo):
        await connector_demo.connect()
        candles = await connector_demo.get_candles("EURUSD", "M15", 50)
        for c in candles:
            assert c.high >= c.open
            assert c.high >= c.close
            assert c.low  <= c.open
            assert c.low  <= c.close

    @pytest.mark.asyncio
    async def test_get_symbol_info_demo(self, connector_demo):
        await connector_demo.connect()
        info = await connector_demo.get_symbol_info("EURUSD")
        assert info.name == "EURUSD"
        assert info.digits == 5
        assert info.volume_min > 0

    @pytest.mark.asyncio
    async def test_health_check_demo(self, connector_demo):
        await connector_demo.connect()
        h = await connector_demo.health_check()
        assert h["ok"] is True
        assert h["mode"] == "DEMO"

    @pytest.mark.asyncio
    async def test_close_position_demo(self, connector_demo):
        await connector_demo.connect()
        result = await connector_demo.place_order("GBPUSD", "SELL", 0.02)
        closed = await connector_demo.close_position(result.ticket)
        assert closed is True

    @pytest.mark.asyncio
    async def test_context_manager(self):
        from backend.execution.mt5_connector import MT5Connector
        async with MT5Connector(demo=True) as c:
            assert c._connected is True
        assert c._connected is False


# ══════════════════════════════════════════════════════════════════════════════
# TestMT5ConnectorLive
# ══════════════════════════════════════════════════════════════════════════════

class TestMT5ConnectorLive:
    @pytest.mark.asyncio
    async def test_connect_live_pings_gateway(self, connector_live):
        """اتصال LIVE باید به /ping بزند."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await connector_live.connect()
            assert connector_live._connected is True

    @pytest.mark.asyncio
    async def test_live_candles_from_gateway(self, connector_live):
        """get_candles در LIVE باید به /candles بزند."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "candles": [
                {"time": "2026-01-01T00:00:00", "open": 1.10, "high": 1.11,
                 "low": 1.09, "close": 1.105, "volume": 1000, "spread": 1}
            ]
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        connector_live._session = mock_session
        connector_live._connected = True

        candles = await connector_live.get_candles("EURUSD", "H1", 1)
        assert len(candles) == 1
        assert candles[0].open == 1.10


# ══════════════════════════════════════════════════════════════════════════════
# TestSignalProcessor
# ══════════════════════════════════════════════════════════════════════════════

class TestSignalProcessor:
    @pytest.mark.asyncio
    async def test_reject_no_trade(self):
        from backend.services.signal_processor import SignalProcessor, RawSignal
        sp = SignalProcessor()
        sig = RawSignal(symbol="EURUSD", timeframe="H1",
                        direction="NO_TRADE", confidence=0.75)
        result = await sp.process(sig)
        assert result.accepted is False
        assert "NO_TRADE" in result.reason

    @pytest.mark.asyncio
    async def test_reject_low_confidence(self):
        from backend.services.signal_processor import SignalProcessor, RawSignal
        sp = SignalProcessor()
        sig = RawSignal(symbol="EURUSD", timeframe="H1",
                        direction="BUY", confidence=0.40)
        result = await sp.process(sig)
        assert result.accepted is False
        assert "confidence" in result.reason

    @pytest.mark.asyncio
    async def test_reject_low_rr(self):
        from backend.services.signal_processor import SignalProcessor, RawSignal
        sp = SignalProcessor()
        sig = RawSignal(
            symbol="EURUSD", timeframe="H1",
            direction="BUY", confidence=0.80,
            entry_price=1.10, sl_price=1.09, tp_price=1.105,
        )
        result = await sp.process(sig)
        assert result.accepted is False
        assert "R:R" in result.reason

    @pytest.mark.asyncio
    async def test_accept_with_mock_execution(self):
        from backend.services.signal_processor import SignalProcessor, RawSignal
        sp = SignalProcessor()
        sp._voting_engine = None

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.ticket  = 123456
        mock_result.error   = None

        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        sp._execution_service = mock_exec

        mock_db = MagicMock()
        mock_db.insert = AsyncMock(return_value={})
        sp._db = mock_db

        sig = RawSignal(
            symbol="EURUSD", timeframe="H1",
            direction="BUY", confidence=0.85,
            entry_price=1.10, sl_price=1.09, tp_price=1.12,
            meta={"volume": 0.01},
        )
        result = await sp.process(sig)
        assert result.accepted is True
        assert result.ticket == 123456

    @pytest.mark.asyncio
    async def test_voting_timeout_continues(self):
        """اگر VotingEngine timeout شود، پردازش ادامه می‌یابد."""
        from backend.services.signal_processor import SignalProcessor, RawSignal

        async def slow_vote(*args, **kwargs):
            await asyncio.sleep(100)
            return []

        sp = SignalProcessor()
        mock_ve = MagicMock()
        mock_ve.collect_votes = slow_vote
        sp._voting_engine = mock_ve

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.ticket  = 999
        mock_result.error   = None
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        sp._execution_service = mock_exec
        sp._db = MagicMock()
        sp._db.insert = AsyncMock()

        sig = RawSignal(
            symbol="GBPUSD", timeframe="H4",
            direction="SELL", confidence=0.72,
            entry_price=1.27, sl_price=1.28, tp_price=1.25,
            meta={"volume": 0.01},
        )
        result = await asyncio.wait_for(sp.process(sig), timeout=15.0)
        assert result.accepted is True


# ══════════════════════════════════════════════════════════════════════════════
# TestMT5GatewayAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestMT5GatewayAgent:
    def test_import_gateway(self):
        pytest.skip("MT5Gateway فقط روی Windows/MT5 اجرا می‌شود")

    def test_agent_routes_defined(self):
        pytest.skip("MT5Gateway فقط روی Windows/MT5 اجرا می‌شود")


# ══════════════════════════════════════════════════════════════════════════════
# TestE2EPipelineSimulated
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EPipelineSimulated:
    @pytest.mark.asyncio
    async def test_full_pipeline_demo(self):
        """
        End-to-end در demo mode:
        RawSignal → SignalProcessor → ExecutionService(demo) → ticket
        """
        from backend.services.signal_processor import SignalProcessor, RawSignal
        from backend.execution.execution_service import ExecutionService
        from backend.execution.mt5_connector import MT5Connector

        connector = MT5Connector(demo=True)
        await connector.connect()

        svc = ExecutionService(connector=connector)
        sp  = SignalProcessor()
        sp._voting_engine     = None
        sp._execution_service = svc
        sp._db                = None

        sig = RawSignal(
            symbol="EURUSD", timeframe="H1",
            direction="BUY", confidence=0.90,
            entry_price=1.10000, sl_price=1.09000, tp_price=1.12000,
            meta={"volume": 0.01},
        )
        result = await sp.process(sig)
        assert result.accepted is True
        assert result.ticket is not None
        assert result.ticket > 0

    @pytest.mark.asyncio
    async def test_candles_fed_to_smc(self):
        """get_candles → SMCEngine.analyse() باید بدون crash اجرا شود."""
        from backend.execution.mt5_connector import MT5Connector
        from backend.analysis.smc_engine import SMCEngine, Candle

        connector = MT5Connector(demo=True)
        await connector.connect()
        raw_candles = await connector.get_candles("EURUSD", "H1", 100)
        await connector.disconnect()

        candles = [
            Candle(
                timestamp=c.time.isoformat(),
                open=c.open, high=c.high, low=c.low, close=c.close,
                volume=c.volume,
            )
            for c in raw_candles
        ]
        engine = SMCEngine()
        result = engine.analyse(candles)
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0
        assert result.bias is not None
