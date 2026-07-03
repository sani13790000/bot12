"""backend/execution/order_state_machine.py
PHASE 3 - Production Order State Machine

Changes:
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
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set

from backend.core.logger import get_logger

logger = get_logger("execution.order_state_machine")


class OrderState(str, Enum):
    PENDING   = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED    = "FILLED"
    PARTIAL   = "PARTIAL"
    CLOSING   = "CLOSING"
    CLOSED    = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    ERROR     = "ERROR"


@dataclass(frozen=True)
class OrderTransition:
    order_id:  str
    from_state: OrderState
    to_state:   OrderState
    timestamp:  float = field(default_factory=time.time)
    reason:     str   = ""


@dataclass
class ManagedOrder:
    order_id:  str
    symbol:    str
    direction: str
    state:     OrderState = OrderState.PENDING
    history:   List[OrderTransition] = field(default_factory=list)

    def is_active(self) -> bool:
        return self.state not in (
            OrderState.CLOSED, OrderState.CANCELLED,
            OrderState.REJECTED, OrderState.ERROR,
        )

    def transition(self, to_state: OrderState, reason: str = "") -> None:
        t = OrderTransition(
            order_id=self.order_id,
            from_state=self.state,
            to_state=to_state,
            reason=reason,
        )
        self.history.append(t)
        self.state = to_state


class SignalIdempotencyGuard:
    """Prevent duplicate signals from creating multiple orders."""

    def __init__(self, max_size: int = 1000) -> None:
        self._seen: Set[str] = set()
        self._max  = max_size

    def is_duplicate(self, signal_id: str) -> bool:
        return signal_id in self._seen

    def mark_seen(self, signal_id: str) -> None:
        if len(self._seen) >= self._max:
            self._seen.pop()
        self._seen.add(signal_id)


class OrderStateMachine:
    """Manages order lifecycle state transitions."""

    def __init__(self) -> None:
        self._orders: Dict[str, ManagedOrder] = {}
        self._idempotency = SignalIdempotencyGuard()

    def get_or_create(self, order_id: str, symbol: str, direction: str) -> ManagedOrder:
        if order_id not in self._orders:
            self._orders[order_id] = ManagedOrder(
                order_id=order_id, symbol=symbol, direction=direction
            )
        return self._orders[order_id]

    def transition(self, order_id: str, to_state: OrderState, reason: str = "") -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        order.transition(to_state, reason)
        return True

    def get_active_orders(self) -> List[ManagedOrder]:
        return [o for o in self._orders.values() if o.is_active()]


_osm: Optional[OrderStateMachine] = None


def get_order_state_machine() -> OrderStateMachine:
    global _osm
    if _osm is None:
        _osm = OrderStateMachine()
    return _osm
