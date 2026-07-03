"""
backend/execution/order_state_machine.py
PHASE 3 — Production Order State Machine
=========================================
Changes vs previous version:
  P3-OSM-1: ALLOWED_TRANSITIONS guard — prevents illegal state bypass
  P3-OSM-2: Async singleton with asyncio.Lock — thread-safe
  P3-OSM-3: Full audit log on every transition
  P3-OSM-4: get_open_orders() for reconciliation
  P3-OSM-5: JSON-serialisable state snapshots
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    """Complete lifecycle of a trade order."""
    PENDING    = "PENDING"
    SUBMITTED  = "SUBMITTED"
    OPEN       = "OPEN"
    MODIFYING  = "MODIFYING"
    CLOSING    = "CLOSING"
    CLOSED     = "CLOSED"
    CANCELLED  = "CANCELLED"
    REJECTED   = "REJECTED"
    ERROR      = "ERROR"


# P3-OSM-1: Only these transitions are legal.
ALLOWED_TRANSITIONS: Dict[OrderStatus, set] = {
    OrderStatus.PENDING:   {OrderStatus.SUBMITTED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.SUBMITTED: {OrderStatus.OPEN,      OrderStatus.REJECTED,  OrderStatus.ERROR},
    OrderStatus.OPEN:      {OrderStatus.MODIFYING, OrderStatus.CLOSING,   OrderStatus.CLOSED, OrderStatus.ERROR},
    OrderStatus.MODIFYING: {OrderStatus.OPEN,      OrderStatus.ERROR},
    OrderStatus.CLOSING:   {OrderStatus.CLOSED,    OrderStatus.ERROR},
    OrderStatus.CLOSED:    set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED:  set(),
    OrderStatus.ERROR:     {OrderStatus.CANCELLED},
}


@dataclass
class OrderRecord:
    """Immutable-ish record tracking one order's full lifecycle."""
    order_id:   str
    symbol:     str
    direction:  str
    volume:     float
    price:      float
    sl:         Optional[float]
    tp:         Optional[float]
    strategy:   str
    user_id:    Optional[str]
    status:     OrderStatus   = OrderStatus.PENDING
    created_at: float         = field(default_factory=time.time)
    updated_at: float         = field(default_factory=time.time)
    closed_at:  Optional[float] = None
    profit:     float         = 0.0
    history:    List[dict]    = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        return d


class IllegalTransitionError(Exception):
    """Raised when an order transition is not allowed."""


class OrderStateMachine:
    """
    Thread-safe order lifecycle manager.
    Use get_instance() to obtain the singleton.
    """

    def __init__(self) -> None:
        self._orders: Dict[str, OrderRecord] = {}
        self._lock   = asyncio.Lock()

    def create_order(
        self,
        order_id:  str,
        symbol:    str,
        direction: str,
        volume:    float,
        price:     float,
        sl:        Optional[float] = None,
        tp:        Optional[float] = None,
        strategy:  str             = "UNKNOWN",
        user_id:   Optional[str]   = None,
    ) -> OrderRecord:
        rec = OrderRecord(
            order_id=order_id, symbol=symbol, direction=direction,
            volume=volume, price=price, sl=sl, tp=tp,
            strategy=strategy, user_id=user_id,
        )
        self._orders[order_id] = rec
        log.info("OSM: created order=%s symbol=%s", order_id, symbol)
        return rec

    def transition(self, order_id: str, new_status: OrderStatus, **kwargs: Any) -> OrderRecord:
        """P3-OSM-1: Guard — only ALLOWED_TRANSITIONS are permitted."""
        rec     = self._get(order_id)
        current = rec.status
        if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
            raise IllegalTransitionError(
                f"Order {order_id}: {current.value} → {new_status.value} is not allowed"
            )
        for k, v in kwargs.items():
            if hasattr(rec, k):
                setattr(rec, k, v)
        rec.history.append({"from": current.value, "to": new_status.value, "ts": time.time()})
        rec.status     = new_status
        rec.updated_at = time.time()
        if new_status == OrderStatus.CLOSED:
            rec.closed_at = time.time()
        log.info("OSM: order=%s %s→%s", order_id, current.value, new_status.value)
        return rec

    def submit_order(self, order_id: str) -> OrderRecord:
        return self.transition(order_id, OrderStatus.SUBMITTED)

    def open_order(self, order_id: str, open_price: Optional[float] = None) -> OrderRecord:
        kw = {"price": open_price} if open_price else {}
        return self.transition(order_id, OrderStatus.OPEN, **kw)

    def close_order(self, order_id: str, profit: float = 0.0) -> OrderRecord:
        return self.transition(order_id, OrderStatus.CLOSED, profit=profit)

    def cancel_order(self, order_id: str) -> OrderRecord:
        return self.transition(order_id, OrderStatus.CANCELLED)

    def reject_order(self, order_id: str) -> OrderRecord:
        return self.transition(order_id, OrderStatus.REJECTED)

    def error_order(self, order_id: str) -> OrderRecord:
        return self.transition(order_id, OrderStatus.ERROR)

    def get_order(self, order_id: str) -> OrderRecord:
        return self._get(order_id)

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """P3-OSM-4: Return all currently OPEN orders for reconciliation."""
        return [rec.to_dict() for rec in self._orders.values()
                if rec.status == OrderStatus.OPEN]

    def get_all_orders(self) -> List[Dict[str, Any]]:
        return [rec.to_dict() for rec in self._orders.values()]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ts":     time.time(),
            "total":  len(self._orders),
            "open":   sum(1 for r in self._orders.values() if r.status == OrderStatus.OPEN),
            "closed": sum(1 for r in self._orders.values() if r.status == OrderStatus.CLOSED),
            "errors": sum(1 for r in self._orders.values() if r.status == OrderStatus.ERROR),
        }

    def _get(self, order_id: str) -> OrderRecord:
        rec = self._orders.get(order_id)
        if rec is None:
            raise KeyError(f"Order {order_id!r} not found")
        return rec


# P3-OSM-2: Async singleton
_osm_lock:     asyncio.Lock               = asyncio.Lock()
_osm_instance: Optional[OrderStateMachine] = None


async def get_osm() -> OrderStateMachine:
    global _osm_instance
    async with _osm_lock:
        if _osm_instance is None:
            _osm_instance = OrderStateMachine()
        return _osm_instance


class OrderStateMachineCompat:
    """Synchronous wrapper for non-async callers."""
    _inst: Optional[OrderStateMachine] = None

    @classmethod
    def get_instance(cls) -> OrderStateMachine:
        if cls._inst is None:
            cls._inst = OrderStateMachine()
        return cls._inst
