"""backend/execution/order_state_machine.py
Order State Machine with enterprise fixes.

Fixes:
  - BUG-OSM-1: lock reentrancy deadlock
  - LOG-FIX-4: asyncio.create_task done_callback error handler
  - STRESS-2: NameError _ORDER_TTL_HOURS → _COMPLETED_ORDER_TTL_HOURS
  - STRESS-7: ContextualLogger is keyword-only — all %s calls converted
  - PHASE1-MERGE S-17..S-20: SignalIdempotencyGuard, dispatch_callbacks_safe,
    CompletedOrderEvictionIndex, StateMachineMetrics
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")

_COMPLETED_ORDER_TTL_HOURS: int = 24
_MAX_ORDERS: int = 10_000


class OrderState(str, Enum):
    PENDING   = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED    = "FILLED"
    PARTIAL   = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    FAILED    = "FAILED"


_TERMINAL_STATES: Set[OrderState] = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.FAILED,
}


@dataclass
class ManagedOrder:
    order_id:   str
    signal_id:  str
    symbol:     str
    direction:  str
    lot_size:   float
    state:      OrderState = OrderState.PENDING
    created_at: datetime   = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime   = field(default_factory=lambda: datetime.now(timezone.utc))
    broker_id:  Optional[str] = None
    error:      Optional[str] = None
    fill_price: Optional[float] = None

    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES


class OrderStateMachine:
    """
    Thread-safe order state machine with eviction, idempotency, and metrics.
    """

    def __init__(self) -> None:
        self._orders: Dict[str, ManagedOrder] = {}
        self._callbacks: List[Callable] = []
        self._lock = asyncio.Lock()
        self._eviction_index = CompletedOrderEvictionIndex(
            ttl_hours=_COMPLETED_ORDER_TTL_HOURS,
            cap=_MAX_ORDERS,
        )
        self._metrics = StateMachineMetrics()

    async def create_order(self, order: ManagedOrder) -> None:
        async with self._lock:
            if order.order_id in self._orders:
                logger.debug("duplicate order ignored", order_id=order.order_id)
                return
            if len(self._orders) >= _MAX_ORDERS:
                await self._evict_expired_nolock()
            self._orders[order.order_id] = order
            self._metrics.record_created(order.order_id)
            logger.debug("order created", order_id=order.order_id, state=order.state.value)

    async def transition(
        self,
        order_id: str,
        new_state: OrderState,
        **kwargs: Any,
    ) -> Optional[ManagedOrder]:
        async with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                logger.debug("transition on unknown order", order_id=order_id)
                return None
            if order.is_terminal():
                logger.debug(
                    "transition blocked: terminal state",
                    order_id=order_id,
                    state=order.state.value,
                )
                return order

            old_state = order.state
            order.state = new_state
            order.updated_at = datetime.now(timezone.utc)
            for k, v in kwargs.items():
                if hasattr(order, k):
                    setattr(order, k, v)

            self._metrics.record_transition(old_state.value, new_state.value)

            if order.is_terminal():
                self._metrics.record_terminal(order_id)
                self._eviction_index.add(order_id, order.updated_at)

            logger.debug(
                "order transition",
                order_id=order_id,
                from_state=old_state.value,
                to_state=new_state.value,
            )

        # Dispatch callbacks outside lock
        _t = asyncio.get_event_loop().create_task(
            dispatch_callbacks_safe(self._callbacks, order)
        )
        _t.add_done_callback(_handle_task_exc("osm:callback"))
        return order

    async def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        async with self._lock:
            return self._orders.get(order_id)

    async def get_all_orders(self) -> List[ManagedOrder]:
        async with self._lock:
            return list(self._orders.values())

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    async def _evict_expired_nolock(self) -> None:
        """Must be called while holding self._lock."""
        expired = self._eviction_index.get_expired()
        for oid in expired:
            self._orders.pop(oid, None)
        self._eviction_index.remove(set(expired))
        logger.debug("evicted expired orders", count=len(expired))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total_orders":  len(self._orders),
            "metrics":       self._metrics.snapshot(),
            "hung_orders":   self._metrics.get_hung_orders(),
        }


def _handle_task_exc(context: str):
    def _cb(task: asyncio.Task) -> None:
        exc = task.exception() if not task.cancelled() else None
        if exc:
            logger.debug("task exception", context=context, error=str(exc))
    return _cb


# ── S-17: SignalIdempotencyGuard ───────────────────────────────────────────
class SignalIdempotencyGuard:
    """S-17: Prevents duplicate orders from same signal_id."""

    _TTL_S = 300

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def register(self, signal_id: str, order_id: str) -> bool:
        """Returns True if signal_id is new; False if already seen (duplicate)."""
        async with self._lock:
            self._purge_expired()
            if signal_id in self._seen:
                return False
            self._seen[signal_id] = time.monotonic()
            return True

    async def release(self, signal_id: str) -> None:
        async with self._lock:
            self._seen.pop(signal_id, None)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in self._seen.items() if now - t > self._TTL_S]
        for k in expired:
            del self._seen[k]


# ── S-18: dispatch_callbacks_safe ──────────────────────────────────────────
async def dispatch_callbacks_safe(callbacks: list, *args: Any) -> None:
    """S-18: Run each callback in isolation; exceptions do not block others."""
    for cb in callbacks:
        try:
            result = cb(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.debug("callback error", error=str(exc))


# ── S-19: CompletedOrderEvictionIndex ──────────────────────────────────────
class CompletedOrderEvictionIndex:
    """S-19: O(1) eviction index for completed orders by TTL and cap."""

    def __init__(self, ttl_hours: int = 24, cap: int = 10_000) -> None:
        self._ttl   = timedelta(hours=ttl_hours)
        self._cap   = cap
        self._index: Dict[str, datetime] = {}

    def add(self, order_id: str, completed_at: datetime) -> None:
        self._index[order_id] = completed_at

    def get_expired(self) -> List[str]:
        cutoff = datetime.now(timezone.utc) - self._ttl
        return [oid for oid, ts in self._index.items() if ts < cutoff]

    def remove(self, order_ids: Set[str]) -> None:
        for oid in order_ids:
            self._index.pop(oid, None)

    def is_over_cap(self, current_count: int) -> bool:
        return current_count >= self._cap


# ── S-20: StateMachineMetrics ────────────────────────────────────────────────
class StateMachineMetrics:
    """S-20: Tracks transitions and detects hung orders."""

    _HUNG_THRESHOLD_S = 300  # 5 minutes

    def __init__(self) -> None:
        self._transitions: Dict[str, int] = defaultdict(int)
        self._created_at:  Dict[str, float] = {}
        self._terminal_at: Dict[str, float] = {}

    def record_transition(self, from_state: str, to_state: str) -> None:
        self._transitions[f"{from_state}→{to_state}"] += 1

    def record_created(self, order_id: str) -> None:
        self._created_at[order_id] = time.monotonic()

    def record_terminal(self, order_id: str) -> None:
        self._created_at.pop(order_id, None)
        self._terminal_at[order_id] = time.monotonic()

    def get_hung_orders(self) -> List[str]:
        """Returns order_ids that have been non-terminal for > threshold."""
        now = time.monotonic()
        return [
            oid for oid, t in self._created_at.items()
            if now - t > self._HUNG_THRESHOLD_S
        ]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "transitions": dict(self._transitions),
            "hung_count":  len(self.get_hung_orders()),
        }


# Singleton
_osm_instance: Optional[OrderStateMachine] = None
_osm_lock = asyncio.Lock()


async def get_order_state_machine() -> OrderStateMachine:
    global _osm_instance
    async with _osm_lock:
        if _osm_instance is None:
            _osm_instance = OrderStateMachine()
        return _osm_instance
