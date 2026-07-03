"""
backend/execution/order_state_machine.py
PHASE 3 — Production Order State Machine

P3-OSM-1: ALLOWED_TRANSITIONS guard
P3-OSM-2: Full lifecycle: PENDING->SUBMITTED->FILLED->CLOSING->CLOSED
P3-OSM-3: OrderTransition immutable audit log per order
P3-OSM-4: action/requested_volume/requested_price fields
P3-OSM-5: is_active() helper
P3-OSM-6: OrderTimeoutWatchdog
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")

_COMPLETED_EVICTION_TTL_S = 300.0


class OrderStatus(str, Enum):
    PENDING    = "PENDING"
    SUBMITTED  = "SUBMITTED"
    FILLED     = "FILLED"
    CLOSING    = "CLOSING"
    CLOSED     = "CLOSED"
    CANCELLED  = "CANCELLED"
    REJECTED   = "REJECTED"


ALLOWED_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.PENDING:   {OrderStatus.SUBMITTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.FILLED:    {OrderStatus.CLOSING, OrderStatus.CLOSED},
    OrderStatus.CLOSING:   {OrderStatus.CLOSED},
    OrderStatus.CLOSED:    set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED:  set(),
}


@dataclass(frozen=True)
class OrderTransition:
    """Immutable audit log entry for a state change."""
    order_id:   str
    from_state: OrderStatus
    to_state:   OrderStatus
    timestamp:  float = field(default_factory=time.time)
    actor:      str   = "system"
    reason:     str   = ""


@dataclass
class Order:
    """Represents a trading order with lifecycle state."""
    order_id:         str
    symbol:           str
    direction:        str
    requested_volume: float
    requested_price:  float
    status:           OrderStatus        = OrderStatus.PENDING
    action:           str                = "OPEN"
    filled_price:     Optional[float]    = None
    filled_volume:    Optional[float]    = None
    ticket:           Optional[int]      = None
    created_at:       float              = field(default_factory=time.time)
    updated_at:       float              = field(default_factory=time.time)
    transitions:      List[OrderTransition] = field(default_factory=list)
    metadata:         Dict[str, Any]     = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status in (
            OrderStatus.PENDING, OrderStatus.SUBMITTED,
            OrderStatus.FILLED, OrderStatus.CLOSING
        )

    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.CLOSED, OrderStatus.CANCELLED, OrderStatus.REJECTED
        )


class StateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""


class StateMachineMetrics:
    def __init__(self):
        self.transitions_total: int = 0
        self.illegal_attempts:  int = 0
        self.active_orders:     int = 0
        self.completed_orders:  int = 0

    def record_transition(self):
        self.transitions_total += 1

    def record_illegal(self):
        self.illegal_attempts += 1


class SignalIdempotencyGuard:
    def __init__(self, maxsize: int = 1000):
        self._seen: deque = deque(maxlen=maxsize)
        self._set:  Set[str] = set()

    def is_duplicate(self, signal_id: str) -> bool:
        return signal_id in self._set

    def register(self, signal_id: str) -> None:
        if len(self._seen) >= self._seen.maxlen:
            old = self._seen.popleft()
            self._set.discard(old)
        self._seen.append(signal_id)
        self._set.add(signal_id)


class CompletedOrderEvictionIndex:
    def __init__(self, ttl_s: float = _COMPLETED_EVICTION_TTL_S):
        self._ttl = ttl_s
        self._index: Dict[str, float] = {}

    def register(self, order_id: str) -> None:
        self._index[order_id] = time.time()

    def evict_expired(self) -> List[str]:
        now = time.time()
        expired = [oid for oid, ts in self._index.items() if now - ts > self._ttl]
        for oid in expired:
            del self._index[oid]
        return expired


class OrderTimeoutWatchdog:
    def __init__(
        self,
        timeout_s: float = 60.0,
        alert_callback: Optional[Callable[[str, OrderStatus], None]] = None,
    ):
        self._timeout_s = timeout_s
        self._alert_cb  = alert_callback
        self._task: Optional[asyncio.Task] = None

    async def start(self, orders: Dict[str, Order]) -> None:
        while True:
            await asyncio.sleep(10)
            now = time.time()
            for order_id, order in list(orders.items()):
                if order.is_active() and (now - order.updated_at) > self._timeout_s:
                    logger.warning(f"Order timeout: {order_id} in {order.status}")
                    if self._alert_cb:
                        try:
                            self._alert_cb(order_id, order.status)
                        except Exception as e:
                            logger.error(f"Timeout alert callback failed: {e}")


class OrderStateMachine:
    """Production order lifecycle manager."""

    def __init__(self):
        self._orders:     Dict[str, Order] = {}
        self._metrics    = StateMachineMetrics()
        self._idempotency = SignalIdempotencyGuard()
        self._eviction   = CompletedOrderEvictionIndex()
        self._lock       = asyncio.Lock()

    async def create_order(
        self,
        order_id: str,
        symbol:   str,
        direction: str,
        volume:   float,
        price:    float,
        **kwargs: Any,
    ) -> Order:
        async with self._lock:
            if order_id in self._orders:
                raise ValueError(f"Order {order_id} already exists")
            order = Order(
                order_id=order_id,
                symbol=symbol,
                direction=direction,
                requested_volume=volume,
                requested_price=price,
                **kwargs,
            )
            self._orders[order_id] = order
            self._metrics.active_orders += 1
            logger.info(f"Order created: {order_id} {direction} {symbol} vol={volume}")
            return order

    async def transition(
        self,
        order_id:   str,
        new_status: OrderStatus,
        actor:      str = "system",
        reason:     str = "",
        **update_fields: Any,
    ) -> Order:
        async with self._lock:
            if order_id not in self._orders:
                raise KeyError(f"Order {order_id} not found")
            order   = self._orders[order_id]
            allowed = ALLOWED_TRANSITIONS.get(order.status, set())
            if new_status not in allowed:
                self._metrics.record_illegal()
                raise StateTransitionError(
                    f"Illegal transition {order.status} -> {new_status} for {order_id}"
                )
            transition = OrderTransition(
                order_id=order_id,
                from_state=order.status,
                to_state=new_status,
                actor=actor,
                reason=reason,
            )
            order.transitions.append(transition)
            order.status     = new_status
            order.updated_at = time.time()
            for k, v in update_fields.items():
                if hasattr(order, k):
                    setattr(order, k, v)
            self._metrics.record_transition()
            if order.is_terminal():
                self._metrics.active_orders   -= 1
                self._metrics.completed_orders += 1
                self._eviction.register(order_id)
            logger.info(f"Order {order_id}: {transition.from_state} -> {new_status}")
            return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    async def get_active_orders(self) -> List[Order]:
        return [o for o in self._orders.values() if o.is_active()]

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "transitions_total": self._metrics.transitions_total,
            "illegal_attempts":  self._metrics.illegal_attempts,
            "active_orders":     self._metrics.active_orders,
            "completed_orders":  self._metrics.completed_orders,
        }


_osm_instance: Optional[OrderStateMachine] = None
_osm_lock = asyncio.Lock()


async def get_order_state_machine() -> OrderStateMachine:
    global _osm_instance
    async with _osm_lock:
        if _osm_instance is None:
            _osm_instance = OrderStateMachine()
        return _osm_instance
