"""
Galaxy Vast AI Trading Platform
Order State Machine — Phase 7

Manages the full lifecycle of every order:
  PENDING -> SUBMITTED -> FILLED / REJECTED / CANCELLED / EXPIRED

Provides:
- immutable audit trail per order
- async-safe transitions
- timeout enforcement
- callback hooks on every state change
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")


class OrderState(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


# Valid transitions: from_state -> set of valid to_states
_TRANSITIONS: Dict[OrderState, set] = {
    OrderState.PENDING: {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.SUBMITTED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELLED},
    OrderState.FILLED: {OrderState.CLOSING},
    OrderState.CLOSING: {OrderState.CLOSED},
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
    OrderState.CLOSED: set(),
}


@dataclass
class OrderTransition:
    from_state: OrderState
    to_state: OrderState
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagedOrder:
    order_id: str
    signal_id: str
    symbol: str
    action: str
    requested_volume: float
    requested_price: float
    stop_loss: float
    take_profit: float
    state: OrderState = OrderState.PENDING
    mt5_ticket: Optional[int] = None
    mt5_deal: Optional[int] = None
    filled_volume: float = 0.0
    filled_price: float = 0.0
    transitions: List[OrderTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_at: Optional[datetime] = None
    last_error: Optional[str] = None

    def is_terminal(self) -> bool:
        return self.state in {
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
            OrderState.CLOSED,
        }

    def is_active(self) -> bool:
        return self.state in {
            OrderState.PENDING,
            OrderState.SUBMITTED,
            OrderState.PARTIALLY_FILLED,
        }

    def duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()


class OrderStateMachine:
    """Thread-safe order state machine with audit trail."""

    def __init__(self, order_timeout_seconds: int = 30) -> None:
        self._orders: Dict[str, ManagedOrder] = {}
        self._lock = asyncio.Lock()
        self._callbacks: List[Callable[[ManagedOrder, OrderTransition], None]] = []
        self._order_timeout = order_timeout_seconds
        self._monitor_task: Optional[asyncio.Task] = None

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    async def start(self) -> None:
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("OrderStateMachine monitor started")

    async def stop(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def create_order(self, order: ManagedOrder) -> ManagedOrder:
        if self._order_timeout:
            order.timeout_at = order.created_at + timedelta(seconds=self._order_timeout)
        async with self._lock:
            self._orders[order.order_id] = order
        logger.info("Order %s created (%s %s)", order.order_id[:8], order.action, order.symbol)
        return order

    async def transition(
        self,
        order_id: str,
        new_state: OrderState,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                logger.warning("Order %s not found", order_id[:8])
                return False

            valid = _TRANSITIONS.get(order.state, set())
            if new_state not in valid:
                logger.error(
                    "Invalid transition %s -> %s for order %s",
                    order.state, new_state, order_id[:8],
                )
                return False

            tr = OrderTransition(
                from_state=order.state,
                to_state=new_state,
                reason=reason,
                metadata=metadata or {},
            )
            order.transitions.append(tr)
            order.state = new_state

        logger.info(
            "Order %s: %s -> %s | %s",
            order_id[:8], tr.from_state, tr.to_state, reason,
        )

        for cb in self._callbacks:
            try:
                result = cb(order, tr)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.error("State machine callback error: %s", exc)

        return True

    async def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        async with self._lock:
            return self._orders.get(order_id)

    async def get_active_orders(self) -> List[ManagedOrder]:
        async with self._lock:
            return [o for o in self._orders.values() if o.is_active()]

    async def get_all_orders(self) -> List[ManagedOrder]:
        async with self._lock:
            return list(self._orders.values())

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                now = datetime.now(timezone.utc)
                async with self._lock:
                    timed_out = [
                        o for o in self._orders.values()
                        if o.is_active()
                        and o.timeout_at
                        and now > o.timeout_at
                    ]
                for order in timed_out:
                    await self.transition(
                        order.order_id, OrderState.EXPIRED, reason="timeout"
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Monitor loop error: %s", exc)


# Singleton
order_state_machine = OrderStateMachine()
