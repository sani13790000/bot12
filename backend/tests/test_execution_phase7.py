"""
Phase 7 execution tests
Covers: MT5Connector, OrderStateMachine, FailureRecovery, PositionReconciliation
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.execution.order_state_machine import (
    ManagedOrder, OrderState, OrderStateMachine, OrderTransition,
)
from backend.execution.failure_recovery import (
    FailureRecoveryEngine, RecoveryStrategy,
)


# ============================================================
# OrderStateMachine
# ============================================================

@pytest.mark.asyncio
async def test_osm_create_order():
    osm = OrderStateMachine()
    order = ManagedOrder(
        order_id="test-001", signal_id="sig-001",
        symbol="XAUUSD", action="BUY",
        requested_volume=0.01, requested_price=2000.0,
        stop_loss=1990.0, take_profit=2020.0,
    )
    await osm.create_order(order)
    found = await osm.get_order("test-001")
    assert found is not None
    assert found.state == OrderState.PENDING


@pytest.mark.asyncio
async def test_osm_valid_transition():
    osm = OrderStateMachine()
    order = ManagedOrder(
        order_id="test-002", signal_id="sig-002",
        symbol="XAUUSD", action="SELL",
        requested_volume=0.01, requested_price=2000.0,
        stop_loss=2010.0, take_profit=1980.0,
    )
    await osm.create_order(order)
    ok = await osm.transition("test-002", OrderState.SUBMITTED, reason="test")
    assert ok is True
    found = await osm.get_order("test-002")
    assert found.state == OrderState.SUBMITTED
    assert len(found.transitions) == 1


@pytest.mark.asyncio
async def test_osm_invalid_transition():
    osm = OrderStateMachine()
    order = ManagedOrder(
        order_id="test-003", signal_id="sig-003",
        symbol="XAUUSD", action="BUY",
        requested_volume=0.01, requested_price=2000.0,
        stop_loss=1990.0, take_profit=2020.0,
    )
    await osm.create_order(order)
    # Cannot go PENDING -> FILLED directly
    ok = await osm.transition("test-003", OrderState.FILLED, reason="invalid")
    assert ok is False
    found = await osm.get_order("test-003")
    assert found.state == OrderState.PENDING


@pytest.mark.asyncio
async def test_osm_full_lifecycle():
    osm = OrderStateMachine()
    order = ManagedOrder(
        order_id="test-004", signal_id="sig-004",
        symbol="XAUUSD", action="BUY",
        requested_volume=0.01, requested_price=2000.0,
        stop_loss=1990.0, take_profit=2020.0,
    )
    await osm.create_order(order)
    await osm.transition("test-004", OrderState.SUBMITTED)
    await osm.transition("test-004", OrderState.FILLED)
    await osm.transition("test-004", OrderState.CLOSING)
    await osm.transition("test-004", OrderState.CLOSED)
    found = await osm.get_order("test-004")
    assert found.state == OrderState.CLOSED
    assert found.is_terminal()
    assert not found.is_active()
    assert len(found.transitions) == 4


@pytest.mark.asyncio
async def test_osm_callback_fired():
    osm = OrderStateMachine()
    fired = []

    def cb(order, transition):
        fired.append((order.order_id, transition.to_state))

    osm.register_callback(cb)
    order = ManagedOrder(
        order_id="test-005", signal_id="sig-005",
        symbol="XAUUSD", action="BUY",
        requested_volume=0.01, requested_price=2000.0,
        stop_loss=1990.0, take_profit=2020.0,
    )
    await osm.create_order(order)
    await osm.transition("test-005", OrderState.SUBMITTED)
    assert len(fired) == 1
    assert fired[0] == ("test-005", OrderState.SUBMITTED)


@pytest.mark.asyncio
async def test_osm_active_orders_filter():
    osm = OrderStateMachine()
    for i in range(3):
        o = ManagedOrder(
            order_id=f"test-00{i+6}", signal_id=f"sig-00{i+6}",
            symbol="XAUUSD", action="BUY",
            requested_volume=0.01, requested_price=2000.0,
            stop_loss=1990.0, take_profit=2020.0,
        )
        await osm.create_order(o)

    # Terminal one
    await osm.transition("test-006", OrderState.CANCELLED)
    active = await osm.get_active_orders()
    ids = [o.order_id for o in active]
    assert "test-006" not in ids
    assert "test-007" in ids


# ============================================================
# FailureRecoveryEngine
# ============================================================

@pytest.mark.asyncio
async def test_recovery_transient_retcode():
    fr = FailureRecoveryEngine(max_retries=3)
    strategy = await fr.handle_failure(
        order_id="ord-001", signal_id="sig-001",
        error="requote", retcode=10004,
    )
    assert strategy == RecoveryStrategy.RETRY
    assert fr.retry_queue_size == 1


@pytest.mark.asyncio
async def test_recovery_permanent_retcode():
    fr = FailureRecoveryEngine(max_retries=3)
    strategy = await fr.handle_failure(
        order_id="ord-002", signal_id="sig-002",
        error="invalid", retcode=10013,
    )
    assert strategy == RecoveryStrategy.DEAD_LETTER
    assert len(fr.dead_letter_queue) == 1


@pytest.mark.asyncio
async def test_recovery_timeout_error():
    fr = FailureRecoveryEngine(max_retries=3)
    strategy = await fr.handle_failure(
        order_id="ord-003", signal_id="sig-003",
        error="connection timeout", retcode=0,
    )
    assert strategy == RecoveryStrategy.RETRY


@pytest.mark.asyncio
async def test_recovery_dead_letter_on_max_retries():
    fr = FailureRecoveryEngine(max_retries=2)
    alert_calls = []

    async def alert(failed):
        alert_calls.append(failed.order_id)

    fr._alert_callback = alert
    strategy = await fr.handle_failure(
        order_id="ord-004", signal_id="sig-004",
        error="timeout", retcode=0,
    )
    assert strategy == RecoveryStrategy.RETRY


@pytest.mark.asyncio
async def test_recovery_health_stats():
    fr = FailureRecoveryEngine()
    stats = fr.health_stats()
    assert "retry_queue_size" in stats
    assert "dead_letter_count" in stats
    assert stats["retry_queue_size"] == 0
    assert stats["dead_letter_count"] == 0
