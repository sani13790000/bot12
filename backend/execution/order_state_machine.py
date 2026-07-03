"""
backend/execution/order_state_machine.py
PHASE 3 — Production Order State Machine
Thread-safe singleton for tracking order lifecycle.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from ..core.logger import get_logger

logger = get_logger("execution.order_state_machine")

_COMPLETED_ORDER_TTL_HOURS: int = 24
_MAX_ORDERS: int = 10_000
_HUNG_THRESHOLD_S: int = 300


class OrderState(str, Enum):
    PENDING   = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL   = "PARTIAL"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    FAILED    = "FAILED"
    HUNG      = "HUNG"


_TRANSITIONS: Dict[OrderState, set] = {
    OrderState.PENDING:   {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.SUBMITTED: {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED, OrderState.HUNG},
    OrderState.PARTIAL:   {OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.HUNG:      {OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.FILLED:    set(),
    OrderState.CANCELLED: set(),
    OrderState.FAILED:    set(),
}

_TERMINAL: frozenset = frozenset({OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED})


class OrderRecord:
    __slots__ = ("order_id", "symbol", "side", "volume", "price", "state", "created_at", "updated_at", "mt5_ticket", "fill_price", "fill_volume", "error_msg", "meta")

    def __init__(self, order_id: str, symbol: str, side: str, volume: float, price: float = 0.0, meta: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.now(timezone.utc)
        self.order_id    = order_id
        self.symbol      = symbol
        self.side        = side
        self.volume      = volume
        self.price       = price
        self.state       = OrderState.PENDING
        self.created_at  = now
        self.updated_at  = now
        self.mt5_ticket: Optional[int]  = None
        self.fill_price: float          = 0.0
        self.fill_volume: float         = 0.0
        self.error_msg: Optional[str]   = None
        self.meta: Dict[str, Any]       = meta or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"order_id": self.order_id, "symbol": self.symbol, "side": self.side, "volume": self.volume, "price": self.price, "state": self.state.value, "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(), "mt5_ticket": self.mt5_ticket, "fill_price": self.fill_price, "fill_volume": self.fill_volume, "error_msg": self.error_msg, "meta": self.meta}


class OrderStateMachineError(RuntimeError):
    pass


class OrderStateMachine:
    def __init__(self) -> None:
        self._orders: Dict[str, OrderRecord] = {}
        self._lock = asyncio.Lock()
        self._log  = logger

    async def register(self, order_id: str, symbol: str, side: str, volume: float, price: float = 0.0, meta: Optional[Dict[str, Any]] = None) -> OrderRecord:
        async with self._lock:
            if order_id in self._orders:
                raise OrderStateMachineError(f"order {order_id!r} already registered")
            if len(self._orders) >= _MAX_ORDERS:
                self._purge_completed_unlocked()
            rec = OrderRecord(order_id, symbol, side, volume, price, meta)
            self._orders[order_id] = rec
            self._log.info("OSM register %s %s %s v=%.2f", order_id, symbol, side, volume)
            return rec

    async def transition(self, order_id: str, new_state: OrderState, *, mt5_ticket: Optional[int] = None, fill_price: Optional[float] = None, fill_volume: Optional[float] = None, error_msg: Optional[str] = None) -> OrderRecord:
        async with self._lock:
            rec = self._get_unlocked(order_id)
            allowed = _TRANSITIONS.get(rec.state, set())
            if new_state not in allowed:
                raise OrderStateMachineError(f"OSM: {order_id!r} cannot transition {rec.state!r} -> {new_state!r}")
            rec.state      = new_state
            rec.updated_at = datetime.now(timezone.utc)
            if mt5_ticket  is not None: rec.mt5_ticket  = mt5_ticket
            if fill_price  is not None: rec.fill_price  = fill_price
            if fill_volume is not None: rec.fill_volume = fill_volume
            if error_msg   is not None: rec.error_msg   = error_msg
            self._log.info("OSM %s -> %s", order_id, new_state.value)
            return rec

    async def get(self, order_id: str) -> Optional[OrderRecord]:
        async with self._lock:
            return self._orders.get(order_id)

    async def get_open_orders(self) -> List[OrderRecord]:
        async with self._lock:
            return [r for r in self._orders.values() if r.state not in _TERMINAL]

    def get_hung_orders(self) -> List[OrderRecord]:
        now = datetime.now(timezone.utc)
        return [r for r in self._orders.values() if r.state == OrderState.HUNG or (r.state == OrderState.SUBMITTED and (now - r.updated_at).total_seconds() > _HUNG_THRESHOLD_S)]

    async def summary(self) -> Dict[str, Any]:
        async with self._lock:
            counts: Dict[str, int] = {}
            for r in self._orders.values():
                counts[r.state.value] = counts.get(r.state.value, 0) + 1
            return {"total": len(self._orders), "counts": counts, "hung_count": len(self.get_hung_orders())}

    def _get_unlocked(self, order_id: str) -> OrderRecord:
        rec = self._orders.get(order_id)
        if rec is None:
            raise OrderStateMachineError(f"order {order_id!r} not found")
        return rec

    def _purge_completed_unlocked(self) -> None:
        now = datetime.now(timezone.utc)
        to_del = [oid for oid, r in self._orders.items() if r.state in _TERMINAL and (now - r.updated_at).total_seconds() > _COMPLETED_ORDER_TTL_HOURS * 3600]
        for oid in to_del:
            del self._orders[oid]
        self._log.info("OSM purged %d completed orders", len(to_del))


_osm_instance: Optional[OrderStateMachine] = None
_osm_lock = asyncio.Lock()


async def get_order_state_machine() -> OrderStateMachine:
    global _osm_instance
    async with _osm_lock:
        if _osm_instance is None:
            _osm_instance = OrderStateMachine()
        return _osm_instance
