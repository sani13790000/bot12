"""
test_03_integration.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های Integration برای:
- Signal → ExecutionService → MT5 → OSM
- PositionReconciler (GHOST / ORPHAN)
- SignalProcessor pipeline کامل
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════ #
# Signal → ExecutionService → OSM                                             #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestFullTradeFlow:
    """پیپلاین کامل: signal → execute → OSM register → close."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_broker, mock_db):
        from backend.execution.execution_service import ExecutionService, TradeSignal

        self.svc = ExecutionService(connector=mock_broker, db=mock_db)
        self.TradeSignal = TradeSignal
        self.broker = mock_broker
        self.db = mock_db

    @pytest.mark.asyncio
    async def test_execute_opens_position(self) -> None:
        sig = self.TradeSignal(
            symbol="EURUSD",
            direction="buy",
            volume=0.10,
            sl=1.1000,
            tp=1.1150,
            confidence=0.82,
            source="test",
        )
        result = await self.svc.execute(sig)
        assert result.success
        assert result.ticket > 0
        self.broker.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_persists_to_db(self) -> None:
        sig = self.TradeSignal(
            symbol="GBPUSD",
            direction="sell",
            volume=0.05,
            sl=1.2800,
            tp=1.2650,
            confidence=0.78,
            source="test",
        )
        await self.svc.execute(sig)
        self.db.insert.assert_called()

    @pytest.mark.asyncio
    async def test_close_position(self) -> None:
        result = await self.svc.close(ticket=999001)
        assert result.success
        self.broker.close_position.assert_called_once_with(999001)

    @pytest.mark.asyncio
    async def test_execute_sell_signal(self) -> None:
        sig = self.TradeSignal(
            symbol="USDJPY",
            direction="sell",
            volume=0.10,
            sl=150.50,
            tp=149.00,
            confidence=0.75,
            source="test",
        )
        result = await self.svc.execute(sig)
        assert result.success

    @pytest.mark.asyncio
    async def test_broker_failure_returns_error(self) -> None:
        self.broker.place_order = AsyncMock(side_effect=Exception("Gateway timeout"))
        sig = self.TradeSignal(
            symbol="EURUSD",
            direction="buy",
            volume=0.10,
            sl=1.1000,
            tp=1.1150,
            confidence=0.80,
            source="test",
        )
        result = await self.svc.execute(sig)
        assert not result.success
        assert result.error != ""


# ═══════════════════════════════════════════════════════════════════════════ #
# PositionReconciler                                                           #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestReconciliationIntegration:
    """تست تشخیص GHOST و ORPHAN positions."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_broker):
        from backend.execution.order_state_machine import OrderStateMachine
        from backend.execution.position_reconciliation import PositionReconciler

        self.osm = OrderStateMachine()
        self.reconciler = PositionReconciler(
            connector=mock_broker,
            osm=self.osm,
            auto_close=False,
        )
        self.broker = mock_broker

    @pytest.mark.asyncio
    async def test_ghost_detection(self) -> None:
        self.osm.register(77001)
        self.osm.transition(77001, "OPEN")
        self.broker.get_open_positions = AsyncMock(return_value=[])
        result = await self.reconciler.run()
        assert result.ghosts >= 1

    @pytest.mark.asyncio
    async def test_orphan_detection(self) -> None:
        self.broker.get_open_positions = AsyncMock(
            return_value=[{"ticket": 88001, "symbol": "EURUSD", "volume": 0.10}]
        )
        result = await self.reconciler.run()
        assert result.orphans >= 1

    @pytest.mark.asyncio
    async def test_no_mismatch_when_in_sync(self) -> None:
        self.osm.register(99001)
        self.osm.transition(99001, "OPEN")
        self.broker.get_open_positions = AsyncMock(
            return_value=[{"ticket": 99001, "symbol": "EURUSD", "volume": 0.10}]
        )
        result = await self.reconciler.run()
        assert result.ghosts == 0
        assert result.orphans == 0

    @pytest.mark.asyncio
    async def test_stats_reported(self) -> None:
        self.broker.get_open_positions = AsyncMock(return_value=[])
        await self.reconciler.run()
        stats = self.reconciler.stats()
        assert "total_runs" in stats


# ═══════════════════════════════════════════════════════════════════════════ #
# SignalProcessor Pipeline                                                     #
# ═══════════════════════════════════════════════════════════════════════════ #
class TestSignalProcessorPipeline:
    @pytest.mark.asyncio
    async def test_reject_no_trade_direction(self) -> None:
        from backend.services.signal_processor import RawSignal, SignalProcessor

        proc = SignalProcessor()
        sig = RawSignal(
            symbol="EURUSD",
            direction="NO_TRADE",
            confidence=0.85,
            entry=1.1050,
            sl=1.1000,
            tp=1.1150,
            lot=0.10,
        )
        result = await proc.process(sig)
        assert not result.executed

    @pytest.mark.asyncio
    async def test_reject_low_confidence(self) -> None:
        from backend.services.signal_processor import RawSignal, SignalProcessor

        proc = SignalProcessor()
        sig = RawSignal(
            symbol="EURUSD",
            direction="BUY",
            confidence=0.30,
            entry=1.1050,
            sl=1.1000,
            tp=1.1150,
            lot=0.10,
        )
        result = await proc.process(sig)
        assert not result.executed
        assert "confidence" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_reject_bad_rr(self) -> None:
        from backend.services.signal_processor import RawSignal, SignalProcessor

        proc = SignalProcessor()
        sig = RawSignal(
            symbol="EURUSD",
            direction="BUY",
            confidence=0.85,
            entry=1.1050,
            sl=1.1048,
            tp=1.1053,
            lot=0.10,
        )
        result = await proc.process(sig)
        assert not result.executed
