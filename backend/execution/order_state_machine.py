"""
Galaxy Vast AI Trading Platform
Order State Machine - Fixed

FIXES:
  T-12:     completed orders evicted after 24h TTL; hard cap 10k
  BUG-OSM-1: DEADLOCK in _monitor_loop - asyncio.Lock is NOT reentrant.
              _monitor_loop held self._lock then called transition() which
              also tries to acquire self._lock -> permanent hang.
              FIX: snapshot timed_out IDs while holding lock, release lock,
              then call transition() without lock.
  BUG-OSM-2: ManagedOrder.requested_price/stop_loss/take_profit typed float
              but execution_service passed None when value was 0.0.
              FIX: fields changed to Optional[float] = 0.0; __post_init__
              normalises None to 0.0.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")
_COMPLETED_ORDER_TTL_HOURS = 24
_MAX_ORDERS = 10_000


class OrderState(str, Enum):
    PENDING          = "PENDING"
    SUBMITTED        = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED           = "FILLED"
    CANCELLED        = "CANCELLED"
    REJECTED         = "REJECTED"
    EXPIRED          = "EXPIRED"
    CLOSING          = "CLOSING"
    CLOSED           = "CLOSED"


_TRANSITIONS: Dict[OrderState, set] = {
    OrderState.PENDING:          {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.SUBMITTED:        {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELLED},
    OrderState.FILLED:           {OrderState.CLOSING},
    OrderState.CLOSING:          {OrderState.CLOSED},
    OrderState.CANCELLED:        set(),
    OrderState.REJECTED:         set(),
    OrderState.EXPIRED:          set(),
    OrderState.CLOSED:           set(),
}
_TERMINAL_STATES = {
    OrderState.FILLED, OrderState.CANCELLED,
    OrderState.REJECTED, OrderState.EXPIRED, OrderState.CLOSED,
}


@dataclass
class OrderTransition:
    from_state: OrderState
    to_state:   OrderState
    timestamp:  datetime          = field(default_factory=lambda: datetime.now(timezone.utc))
    reason:     str               = ""
    metadata:   Dict[str, Any]    = field(default_factory=dict)


@dataclass
class ManagedOrder:
    order_id:         str
    signal_id:        str
    symbol:           str
    action:           str
    requested_volume: float
    # BUG-OSM-2 FIX: Optional[float] with default 0.0 to accept None from
    # execution_service retry path. 0.0 means market order / broker default.
    requested_price:  Optional[float] = 0.0
    stop_loss:        Optional[float] = 0.0
    take_profit:      Optional[float] = 0.0
    state:            OrderState      = OrderState.PENDING
    mt5_ticket:       Optional[int]   = None
    mt5_deal:         Optional[int]   = None
    filled_volume:    float           = 0.0
    filled_price:     float           = 0.0
    transitions:      List[OrderTransition] = field(default_factory=list)
    created_at:       datetime        = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at:     Optional[datetime] = None
    timeout_at:       Optional[datetime] = None
    last_error:       Optional[str]   = None

    def __post_init__(self) -> None:
        if self.requested_price is None:
            self.requested_price = 0.0
        if self.stop_loss is None:
            self.stop_loss = 0.0
        if self.take_profit is None:
            self.take_profit = 0.0

    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    def is_active(self) -> bool:
        return self.state in {OrderState.PENDING, OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED}

    def duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()


class OrderStateMachine:
    def __init__(
        self,
        order_timeout_seconds: int = 30,
        completed_ttl_hours:   int = _COMPLETED_ORDER_TTL_HOURS,
    ) -> None:
        self._orders:        Dict[str, ManagedOrder] = {}
        self._lock           = asyncio.Lock()
        self._callbacks:     List[Callable]          = []
        self._order_timeout  = order_timeout_seconds
        self._completed_ttl  = timedelta(hours=completed_ttl_hours)
        self._monitor_task:  Optional[asyncio.Task]  = None

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    async def start(self) -> None:
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("OrderStateMachine monitor started ttl=%dh", _COMPLETED_ORDER_TTL_HOURS)

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
            if len(self._orders) >= _MAX_ORDERS:
                self._evict_oldest_completed()
            self._orders[order.order_id] = order
        logger.info("Order %s created %s %s", order.order_id[:8], order.action, order.symbol)
        return order

    async def transition(
        self,
        order_id:  str,
        new_state: OrderState,
        reason:    str = "",
        metadata:  Optional[Dict[str, Any]] = None,
    ) -> bool:
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                logger.warning("Order %s not found", order_id[:8])
                return False
            valid = _TRANSITIONS.get(order.state, set())
            if new_state not in valid:
                logger.error("Invalid transition %s->%s order %s", order.state, new_state, order_id[:8])
                return False
            tr = OrderTransition(
                from_state=order.state, to_state=new_state,
                reason=reason, metadata=metadata or {},
            )
            order.transitions.append(tr)
            order.state = new_state
            if new_state in _TERMINAL_STATES:
                order.completed_at = datetime.now(timezone.utc)
        logger.info("Order %s: %s->%s | %s", order_id[:8], tr.from_state, tr.to_state, reason)
        for cb in self._callbacks:
            try:
                result = cb(order, tr)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.error("Callback error: %s", exc)
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

    def _evict_oldest_completed(self) -> None:
        """Must be called while holding self._lock."""
        now = datetime.now(timezone.utc)
        to_remove = [
            oid for oid, o in self._orders.items()
            if o.is_terminal() and o.completed_at and (now - o.completed_at) > self._completed_ttl
        ]
        for oid in to_remove:
            del self._orders[oid]
        if to_remove:
            logger.info("Evicted %d completed orders", len(to_remove))

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                now = datetime.now(timezone.utc)

                # BUG-OSM-1 FIX: asyncio.Lock is NOT reentrant.
                # OLD: held lock -> called transition() -> transition() tried to
                #   acquire same lock -> permanent hang on same asyncio Task.
                # FIX: collect order IDs while holding lock, release lock,
                #   THEN call transition() which acquires lock fresh.
                async with self._lock:
                    timed_out_ids = [
                        o.order_id
                        for o in self._orders.values()
                        if o.is_active() and o.timeout_at and now > o.timeout_at
                    ]

                # Lock released - transition() acquires independently
                for order_id in timed_out_ids:
                    await self.transition(order_id, OrderState.EXPIRED, reason="timeout")

                # Eviction: separate lock acquisition
                async with self._lock:
                    self._evict_oldest_completed()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Monitor loop error: %s", exc)


order_state_machine = OrderStateMachine()
