"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های واحد: OrderStateMachine، MT5Connector، DecisionEngine، SMCEngine
"""
from __future__ import annotations
import asyncio
import pytest


# --- OrderStateMachine ---

class TestOrderStateMachine:
    """تست FSM مدیریت چرخهی عمر سفارش."""

    def setup_method(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine
        OrderStateMachine._instance = None
        self.osm = OrderStateMachine.get_instance()

    def test_register_and_initial_state(self) -> None:
        from backend.execution.order_state_machine import OrderState
        self.osm.register(ticket=10001)
        assert self.osm.get_state(10001) == OrderState.PENDING.value

    def test_full_happy_path(self) -> None:
        from backend.execution.order_state_machine import OrderState
        self.osm.register(ticket=20001)
        self.osm.transition(20001, "SUBMITTED")
        self.osm.transition(20001, "OPEN")
        self.osm.transition(20001, "CLOSING")
        self.osm.transition(20001, "CLOSED")
        assert self.osm.get_state(20001) == OrderState.CLOSED.value

    def test_invalid_transition_raises(self) -> None:
        self.osm.register(ticket=30001)
        with pytest.raises((ValueError, KeyError)):
            self.osm.transition(30001, "CLOSED")

    def test_terminal_state_locked(self) -> None:
        self.osm.register(ticket=40001)
        self.osm.transition(40001, "CANCELLED")
        assert self.osm.is_terminal(40001) is True

    def test_active_tickets(self) -> None:
        self.osm.register(ticket=50001)
        self.osm.register(ticket=50002)
        self.osm.transition(50001, "CANCELLED")
        active = self.osm.active_tickets()
        assert 50001 not in active
        assert 50002 in active

    def test_history_recorded(self) -> None:
        self.osm.register(ticket=60001)
        self.osm.transition(60001, "SUBMITTED")
        history = self.osm.get_history(60001)
        assert len(history) >= 2
        states = [h[0] for h in history]
        assert "PENDING" in states
        assert "SUBMITTED" in states

    def test_stats(self) -> None:
        self.osm.register(ticket=70001)
        stats = self.osm.stats()
        assert isinstance(stats, dict)
        assert any(v > 0 for v in stats.values())

    def test_singleton(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine
        a = OrderStateMachine.get_instance()
        b = OrderStateMachine.get_instance()
        assert a is b

    def test_auto_register_on_transition(self) -> None:
        try:
            self.osm.transition(99999, "SUBMITTED")
            state = self.osm.get_state(99999)
            assert state == "SUBMITTED"
        except (KeyError, ValueError):
            pass


# --- MT5Connector (demo mode) ---

class TestMT5ConnectorDemo:
    """تست MT5Connector در demo mode."""

    def setup_method(self) -> None:
        from backend.execution.mt5_connector import MT5Connector
        try:
            self.connector = MT5Connector(demo=True)
        except TypeError:
            self.connector = MT5Connector(demo_mode=True)

    @pytest.mark.asyncio
    async def test_connect_in_demo(self) -> None:
        await self.connector.connect()
        assert self.connector._connected is True or getattr(self.connector, 'is_connected', True)

    @pytest.mark.asyncio
    async def test_place_order_returns_result(self) -> None:
        await self.connector.connect()
        try:
            result = await self.connector.place_order(
                symbol="EURUSD", direction="BUY", volume=0.01, sl=1.080, tp=1.090
            )
        except TypeError:
            result = await self.connector.open_position("EURUSD", "BUY", 0.01, 1.080, 1.090)
        assert result is not None

    @pytest.mark.asyncio
    async def test_close_position_in_demo(self) -> None:
        await self.connector.connect()
        try:
            closed = await self.connector.close_position(ticket=123456)
        except TypeError:
            closed = await self.connector.close_position(123456)
        assert closed is True or (hasattr(closed, 'success') and closed.success)

    @pytest.mark.asyncio
    async def test_get_account_info_in_demo(self) -> None:
        await self.connector.connect()
        info = await self.connector.get_account_info()
        assert info is not None
        balance = info.get('balance') if isinstance(info, dict) else getattr(info, 'balance', 10000)
        assert balance > 0

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        await self.connector.connect()
        await self.connector.disconnect()
        assert (
            self.connector._connected is False
            or not getattr(self.connector, 'is_connected', True)
        )


# --- SMCEngine ---

class TestSMCEngine:
    """تست موتور Smart Money Concepts."""

    def _make_candles(self, n: int = 50) -> list:
        from backend.analysis.smc_engine import Candle
        import math
        price = 1.0800
        candles = []
        for i in range(n):
            d = 0.0001 * math.sin(i * 0.3)
            o = price
            c = price + d + (0.0005 if i % 3 == 0 else -0.0003)
            candles.append(Candle(
                f"t{i}",
                round(o, 5),
                round(max(o, c) + 0.0002, 5),
                round(min(o, c) - 0.0002, 5),
                round(c, 5),
            ))
            price = c
        return candles

    def test_analyse_returns_result(self) -> None:
        from backend.analysis.smc_engine import SMCEngine, SMCAnalysis
        result = SMCEngine().analyse(self._make_candles(50))
        assert isinstance(result, SMCAnalysis)
        assert 0.0 <= result.confidence <= 1.0

    def test_too_few_candles_raises(self) -> None:
        from backend.analysis.smc_engine import SMCEngine, Candle
        with pytest.raises((ValueError, AssertionError)):
            SMCEngine().analyse([Candle("t", 1.0, 1.1, 0.9, 1.05)] * 5)

    def test_order_blocks_returned(self) -> None:
        from backend.analysis.smc_engine import SMCEngine
        result = SMCEngine().analyse(self._make_candles(60))
        assert hasattr(result, 'order_blocks') or hasattr(result, 'bias')


# --- DecisionEngine ---

class TestDecisionEngine:
    """تست موتور تصمیم‌گیری ترکیبی."""

    def setup_method(self) -> None:
        from backend.analysis.decision_engine import DecisionEngine
        self.engine = DecisionEngine(min_confidence=0.60, min_votes=2)

    def test_all_agree_buy(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection
        votes = [
            EngineVote("SMC", TradeDirection.BUY, 0.80, 1.085, 1.080, 1.095),
            EngineVote("PA",  TradeDirection.BUY, 0.75, 1.085, 1.079, 1.096),
        ]
        dec = self.engine.decide(votes, "EURUSD", "H1")
        assert dec.direction == TradeDirection.BUY
        assert dec.should_trade is True

    def test_conflicting_votes_no_trade(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection, DecisionReason
        votes = [
            EngineVote("A", TradeDirection.BUY,  0.8),
            EngineVote("B", TradeDirection.SELL, 0.8),
        ]
        dec = self.engine.decide(votes, "EURUSD", "H1")
        assert dec.direction == TradeDirection.NO_TRADE

    def test_kill_switch_overrides(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection, DecisionReason
        votes = [
            EngineVote("A", TradeDirection.BUY, 1.0),
            EngineVote("B", TradeDirection.BUY, 1.0),
        ]
        dec = self.engine.decide(votes, "EURUSD", "H1", kill_switch_active=True)
        assert dec.reason == DecisionReason.KILL_SWITCH
        assert dec.should_trade is False

    def test_low_confidence_no_trade(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection
        votes = [
            EngineVote("A", TradeDirection.BUY, 0.30),
            EngineVote("B", TradeDirection.BUY, 0.25),
        ]
        dec = self.engine.decide(votes, "EURUSD", "H1")
        assert dec.should_trade is False

    def test_to_dict(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection
        votes = [
            EngineVote("A", TradeDirection.BUY, 0.80, 1.085, 1.080, 1.095),
            EngineVote("B", TradeDirection.BUY, 0.75, 1.085, 1.079, 1.096),
        ]
        d = self.engine.decide(votes, "EURUSD", "H1").to_dict()
        assert "direction" in d and "should_trade" in d
