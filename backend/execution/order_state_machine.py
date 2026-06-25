"""backend/execution/order_state_machine.py
Order State Machine with enterprise fixes.

Fixes:
  - BUG-OSM-1: lock reentrancy deadlock (collect IDs, release lock, then transition)
  - LOG-FIX-4: asyncio.create_task(result) ⁵ track with done_callback error handler
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")

_COMPLETED_ORDER_TTL_HOURS: int = 24


class OrderState(Enum):
    PENDING   = "pending"
    SUBMITTED = "submitted"
    FILLED    = "filled"
    CANCELLED = "cancelled"
    FAILED    = "failed"


_TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED}


@dataclass
class StateTransition:
    from_state: OrderState
    to_state:   OrderState
    reason:     str = ""


_VALID_TRANSITIONS: Dict[OrderState, Set[OrderState]] = {
    OrderState.PENDING:   {OrderState.SUBMITTED, OrderState.FAILED, OrderState.CANCELLED},
    OrderState.SUBMITTED: {OrderState.FILLED, OrderState.FAILED, OrderState.CANCELLED},
    OrderState.FILLED:    set(),
    OrderState.CANCELLED: set(),
    OrderState.FAILED:    set(),
}


@dataclass
class ManagedOrder:
    order_id:        str
    symbol:          str
    direction:       str
    lots:            float
    state:           OrderState = OrderState.PENDING
    metadata:        Dict[rstr, Any] = field(default_factory=dict)
    created_at:      datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at:    Optional[datetime] = None
    retcode:         int = 0
    ticket:          Optional[str] = None

    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES


def _handle_task_exc(name: str):
    """Reusable done_callback that logs task exceptions."""
    def _cb(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception():
            logger.error("%s task failed: %s", name, t.exception(), exc_info=t.exception())
    return _cb


class OrderStateMachine:
    """Thread-safe async Order State Machine."""

    def __init__(
        self,
        order_timeout_seconds: int = 300,
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
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(), name="osm:monitor"
        )
        self._monitor_task.add_done_callback(_handle_task_exc("osm:monitor"))
        logger.info("OrderStateMachine monitor started ttl=%dh", _COMPLETED=_ORDER_TTL_HOURS)

    async def stop(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("OrderStateMachine stopped")

    async def register_order(self, order: ManagedOrder) -> None:
        async with self._lock:
            self._orders[order.order_id] = order
        logger.info("Order registered %s %s %s %s", order.order_id[:8], order.symbol, order.direction, order.lots)

    async def transition(self, order_id: str, new_state: OrderState, reason: str = "", **kw) -> bool:
        async with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                logger.warning("Order %s not found", order_id[:8])
                return False
            allowed = _VALID_TRANSITIONS.get(order.state, set())
            if new_state not in allowed:
                logger.warning("Invalid transition %s: %s->%s", order_id[:8], order.state, new_state)
                return False
            tr = StateTransition(from_state=order.state, to_state=new_state, reason=reason)
            for k, v in kw.items():
                if hasattr(order, k): setattr(order, k, v)
            order.state = new_state
            if new_state in _TERMINAL_STATES:
                order.completed_at = datetime.now(timezone.utc)
        logger.info("Order %s: %s->%s | %s", order_id[:8], tr.from_state, tr.to_state, reason)
        for cb in self._callbacks:
            try:
                result = cb(order, tr)
                if asyncio.iscoroutine(result):
                    _t = asyncio.create_task(result, name="osm:callback")  # LOG-FIX-4: track task
                    _t.add_done_callback(_handle_task_exc("osm:callback"))
            except Exception as exc:
                logger.error("Callback error: %s", exc)
        return True

    async def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        async with self._lock:
            return self._orders.get(order_id)

    async def list_orders(self, state: Optional[OrderState] = None) -> List[ManagedOrder]:
        async with self._lock:
            orders = list(self._orders.values())
        return [o for o in orders if state is None or o.state == state]

    def snapshot(self) -> Dict:
        return {
            "total":     len(self._orders),
            "pending":   sum(1 for o in self._orders.values() if o.state == OrderState.PENDING),
            "filled":    sum(1 for o in self._orders.values() if o.state == OrderState.FILLED),
            "failed":    sum(1 for o in self._orders.values() if o.state == OrderState.FAILED),
            "cancelled": sum(1 for o in self._orders.values() if o.state == OrderState.CANCELLED),
        }

    async def _evict_completed(self, now: datetime) -> None:
        async with self._lock:
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
                async with self._lock:
                    timed_out_ids = [
                        o.order_id for o in self._orders.values()
                        if o.state == OrderState.SUBMITTED
                        and (now - o.created_at).total_seconds() > self._order_timeout
                    ]
                for oid in timed_out_ids:
                    await self.transition(oid, OrderState.FAILED, reason="timeout")
                await self._evict_completed(now)
            except asyncio.CancelledError:
                logger.info("OrderStateMachine monitor cancelled")
                break
            except Exception as exc:
                logger.error("OSM monitor loop error: %s", exc, exc_info=True)
                await asyncio.sleep(5)
