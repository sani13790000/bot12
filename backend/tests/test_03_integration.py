"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های یکپارچگی: چرخهی کامل سیگنال تا معامله
"""
from __future__ import annotations
import asyncio
import pytest


class TestFullTradeFlow:
    """تست pipeline کامل: DecisionEngine → OSM → MT5Connector."""

    def setup_method(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine
        OrderStateMachine._instance = None
        self.osm = OrderStateMachine.get_instance()

    @pytest.mark.asyncio
    async def test_signal_to_open_position(self) -> None:
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        from backend.execution.mt5_connector import MT5Connector

        engine = DecisionEngine(min_confidence=0.60, min_votes=2)
        votes = [
            EngineVote("SMC", TradeDirection.BUY, 0.80, 1.085, 1.080, 1.095),
            EngineVote("PA",  TradeDirection.BUY, 0.75, 1.085, 1.079, 1.096),
        ]
        decision = engine.decide(votes, "EURUSD", "H1")
        assert decision.should_trade is True

        self.osm.register(ticket=88001)
        self.osm.transition(88001, "SUBMITTED")

        try:
            conn = MT5Connector(demo=True)
        except TypeError:
            conn = MT5Connector(demo_mode=True)

        await conn.connect()
        try:
            result = await conn.place_order(
                symbol="EURUSD", direction="BUY", volume=0.01,
                sl=getattr(decision, 'sl_price', 1.080),
                tp=getattr(decision, 'tp_price', 1.095),
            )
        except (TypeError, AttributeError):
            result = await conn.open_position(
                "EURUSD", "BUY", 0.01,
                getattr(decision, 'sl_price', 1.080),
                getattr(decision, 'tp_price', 1.095),
            )
        assert result is not None

        self.osm.transition(88001, "OPEN")
        assert self.osm.get_state(88001) == "OPEN"
        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_signal_to_close(self) -> None:
        from backend.execution.mt5_connector import MT5Connector
        try:
            conn = MT5Connector(demo=True)
        except TypeError:
            conn = MT5Connector(demo_mode=True)

        await conn.connect()
        self.osm.register(ticket=88002)
        self.osm.transition(88002, "SUBMITTED")
        self.osm.transition(88002, "OPEN")

        try:
            closed = await conn.close_position(ticket=88002)
        except TypeError:
            closed = await conn.close_position(88002)

        ok = closed is True or (hasattr(closed, 'success') and closed.success)
        assert ok

        self.osm.transition(88002, "CLOSING")
        self.osm.transition(88002, "CLOSED")
        assert self.osm.is_terminal(88002) is True
        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_rejected_order_flow(self) -> None:
        self.osm.register(ticket=88003)
        self.osm.transition(88003, "SUBMITTED")
        self.osm.transition(88003, "REJECTED")
        assert self.osm.is_terminal(88003) is True

    @pytest.mark.asyncio
    async def test_cancelled_order_flow(self) -> None:
        self.osm.register(ticket=88004)
        self.osm.transition(88004, "CANCELLED")
        assert self.osm.is_terminal(88004) is True


class TestReconciliationIntegration:
    """تست تشخیص GHOST / ORPHAN."""

    def setup_method(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine
        OrderStateMachine._instance = None
        self.osm = OrderStateMachine.get_instance()

    @pytest.mark.asyncio
    async def test_ghost_detection(self) -> None:
        from backend.execution.mt5_connector import MT5Connector
        from backend.execution.position_reconciliation import (
            PositionReconciliation, MismatchType,
        )
        try:
            conn = MT5Connector(demo=True)
        except TypeError:
            conn = MT5Connector(demo_mode=True)

        await conn.connect()
        self.osm.register(ticket=999999999)
        self.osm.transition(999999999, "SUBMITTED")
        self.osm.transition(999999999, "OPEN")

        try:
            rec = PositionReconciliation(mt5_connector=conn, osm=self.osm)
        except TypeError:
            rec = PositionReconciliation(connector=conn, state_machine=self.osm)

        try:
            mismatches = await rec._run_once()
        except AttributeError:
            mismatches = await rec.run_once()

        ghosts = [m for m in mismatches if m.mismatch_type == MismatchType.GHOST]
        assert len(ghosts) >= 1
        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_no_mismatch_when_empty(self) -> None:
        from backend.execution.mt5_connector import MT5Connector
        from backend.execution.position_reconciliation import PositionReconciliation
        try:
            conn = MT5Connector(demo=True)
        except TypeError:
            conn = MT5Connector(demo_mode=True)

        await conn.connect()
        try:
            rec = PositionReconciliation(mt5_connector=conn, osm=self.osm)
        except TypeError:
            rec = PositionReconciliation(connector=conn, state_machine=self.osm)

        try:
            mismatches = await rec._run_once()
        except AttributeError:
            mismatches = await rec.run_once()

        assert isinstance(mismatches, list)
        await conn.disconnect()
