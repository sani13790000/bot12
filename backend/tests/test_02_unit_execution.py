"""
test_02_unit_execution.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های unit برای:
- OrderStateMachine (با API واقعی: register/transition/get_state)
- MT5Connector (demo mode)
- SMCEngine
- DecisionEngine
"""
from __future__ import annotations

import os
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from typing import List


# ═══════════════════════════════════════════════════════════════════════════ #
# OrderStateMachine                                                           #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestOrderStateMachine:
    """تست کامل FSM با API واقعی — register/transition/get_state."""

    def setup_method(self):
        from backend.execution.order_state_machine import OrderStateMachine
        self.osm = OrderStateMachine()

    def test_register_and_initial_state(self) -> None:
        self.osm.register(10001)
        assert self.osm.get_state(10001) == "PENDING"

    def test_full_happy_path(self) -> None:
        self.osm.register(10002)
        self.osm.transition(10002, "OPEN")
        self.osm.transition(10002, "CLOSED")
        assert self.osm.get_state(10002) == "CLOSED"
        assert self.osm.is_terminal(10002)

    def test_invalid_transition_raises(self) -> None:
        self.osm.register(10003)
        with pytest.raises(Exception):
            self.osm.transition(10003, "INVALID_STATE_XYZ")

    def test_terminal_state_locked(self) -> None:
        self.osm.register(10004)
        self.osm.transition(10004, "REJECTED")
        assert self.osm.is_terminal(10004)
        with pytest.raises(Exception):
            self.osm.transition(10004, "OPEN")

    def test_active_tickets(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.register(20001)
        osm.register(20002)
        assert 20001 in osm.active_tickets
        assert 20002 in osm.active_tickets

    def test_history_recorded(self) -> None:
        self.osm.register(10005)
        self.osm.transition(10005, "OPEN")
        history = self.osm.get_history(10005)
        assert any("PENDING" in str(h) for h in history)

    def test_stats(self) -> None:
        self.osm.register(10006)
        stats = self.osm.stats()
        assert "total" in stats

    def test_module_level_singleton(self) -> None:
        from backend.execution.order_state_machine import order_state_machine
        assert order_state_machine is not None

    def test_cancelled_path(self) -> None:
        self.osm.register(10007)
        self.osm.transition(10007, "CANCELLED")
        assert self.osm.is_terminal(10007)

    def test_error_path(self) -> None:
        self.osm.register(10008)
        self.osm.transition(10008, "OPEN")
        self.osm.transition(10008, "ERROR")
        assert self.osm.is_terminal(10008)


# ═══════════════════════════════════════════════════════════════════════════ #
# MT5Connector — Demo Mode                                                    #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestMT5ConnectorDemo:
    """تست connector در demo mode."""

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["MT5_DEMO_MODE"] = "true"
        from backend.execution.mt5_connector import MT5Connector
        self.connector = MT5Connector(demo=True)

    @pytest.mark.asyncio
    async def test_connect_in_demo(self) -> None:
        result = await self.connector.connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_place_order_returns_ticket(self) -> None:
        await self.connector.connect()
        result = await self.connector.place_order(
            symbol="EURUSD", direction="buy",
            volume=0.10, sl=1.1000, tp=1.1150
        )
        assert "ticket" in result
        assert isinstance(result["ticket"], int)
        assert result["ticket"] > 0

    @pytest.mark.asyncio
    async def test_close_position_in_demo(self) -> None:
        await self.connector.connect()
        result = await self.connector.close_position(ticket=999001)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_account_info_in_demo(self) -> None:
        await self.connector.connect()
        info = await self.connector.get_account_info()
        assert "balance" in info
        assert info["balance"] > 0

    @pytest.mark.asyncio
    async def test_get_candles_returns_list(self) -> None:
        await self.connector.connect()
        candles = await self.connector.get_candles("EURUSD", "H1", 50)
        assert isinstance(candles, list)
        assert len(candles) == 50

    @pytest.mark.asyncio
    async def test_get_candles_ohlc_structure(self) -> None:
        await self.connector.connect()
        candles = await self.connector.get_candles("EURUSD", "H1", 10)
        for c in candles:
            assert "open" in c and "high" in c and "low" in c and "close" in c

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        await self.connector.connect()
        await self.connector.disconnect()
        assert self.connector.connected is False

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        from backend.execution.mt5_connector import MT5Connector
        async with MT5Connector(demo=True) as conn:
            assert conn.connected is True


# ═══════════════════════════════════════════════════════════════════════════ #
# SMCEngine                                                                    #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestSMCEngine:
    """تست موتور SMC با کندل‌های مصنوعی."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from backend.analysis.smc_engine import SMCEngine, Candle
        self.engine = SMCEngine()
        self.Candle = Candle
        self.candles = [
            Candle(
                time=1_700_000_000 + i * 3600,
                open=1.1000 + i * 0.0001,
                high=1.1010 + i * 0.0001 + (0.002 if i % 10 == 5 else 0),
                low=1.0990 + i * 0.0001 - (0.002 if i % 10 == 3 else 0),
                close=1.1005 + i * 0.0001,
                tick_volume=500 + i,
            )
            for i in range(150)
        ]

    def test_analyse_returns_result(self) -> None:
        from backend.analysis.smc_engine import SMCAnalysis
        result = self.engine.analyse(self.candles)
        assert isinstance(result, SMCAnalysis)

    def test_too_few_candles_raises(self) -> None:
        with pytest.raises(Exception):
            self.engine.analyse(self.candles[:5])

    def test_order_blocks_returned(self) -> None:
        result = self.engine.analyse(self.candles)
        assert hasattr(result, "order_blocks")
        assert isinstance(result.order_blocks, list)

    def test_fvg_returned(self) -> None:
        result = self.engine.analyse(self.candles)
        assert hasattr(result, "fair_value_gaps")

    def test_bias_returned(self) -> None:
        result = self.engine.analyse(self.candles)
        assert hasattr(result, "bias")

    def test_confidence_in_range(self) -> None:
        result = self.engine.analyse(self.candles)
        assert 0.0 <= result.confidence <= 1.0


# ═══════════════════════════════════════════════════════════════════════════ #
# DecisionEngine                                                               #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestDecisionEngine:
    """تست موتور تصمیم‌گیری."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        self.engine = DecisionEngine(min_confidence=0.65, min_votes=2, min_rr=1.5)
        self.EngineVote = EngineVote
        self.TradeDirection = TradeDirection

    def test_all_agree_buy(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.80, 1.1050, 1.1000, 1.1150),
            self.EngineVote("PA",  self.TradeDirection.BUY, 0.75, 1.1050, 1.1000, 1.1150),
            self.EngineVote("XGB", self.TradeDirection.BUY, 0.85, 1.1050, 1.1000, 1.1150),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1")
        assert d.direction == self.TradeDirection.BUY
        assert d.should_trade

    def test_conflicting_votes_no_trade(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY,  0.80),
            self.EngineVote("PA",  self.TradeDirection.SELL, 0.80),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1")
        assert not d.should_trade

    def test_kill_switch_overrides(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.95, 1.1050, 1.1000, 1.1200),
            self.EngineVote("PA",  self.TradeDirection.BUY, 0.90, 1.1050, 1.1000, 1.1200),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1", kill_switch_active=True)
        assert not d.should_trade

    def test_low_confidence_no_trade(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.40),
            self.EngineVote("PA",  self.TradeDirection.BUY, 0.35),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1")
        assert not d.should_trade

    def test_to_dict(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.SELL, 0.80, 1.1050, 1.1100, 1.1000),
            self.EngineVote("PA",  self.TradeDirection.SELL, 0.75, 1.1050, 1.1100, 1.1000),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1")
        result = d.to_dict()
        assert "direction" in result
        assert "confidence" in result
        assert "should_trade" in result

    def test_minimum_rr_enforced(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.80, 1.1050, 1.1048, 1.1060),
            self.EngineVote("PA",  self.TradeDirection.BUY, 0.80, 1.1050, 1.1048, 1.1060),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1")
        assert not d.should_trade
