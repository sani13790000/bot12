"""
backend/execution/order_state_machine.py
Galaxy Vast AI - Order State Machine (thread-safe singleton)

Transitions: PENDING->SUBMITTED->FILLED->CLOSED
             Any->CANCELLED, Any->ERROR
             FILLED->PARTIALLY_CLOSED->CLOSED
"""
from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderState(str, Enum):
    PENDING          = "PENDING"
    SUBMITTED        = "SUBMITTED"
    FILLED           = "FILLED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED           = "CLOSED"
    CANCELLED        = "CANCELLED"
    ERROR            = "ERROR"


_ALLOWED: Dict[OrderState, List[OrderState]] = {
    OrderState.PENDING:          [OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.ERROR],
    OrderState.SUBMITTED:        [OrderState.FILLED,    OrderState.CANCELLED, OrderState.ERROR],
    OrderState.FILLED:           [OrderState.PARTIALLY_CLOSED, OrderState.CLOSED, OrderState.ERROR],
    OrderState.PARTIALLY_CLOSED: [OrderState.CLOSED, OrderState.ERROR],
    OrderState.CLOSED:    [],
    OrderState.CANCELLED: [],
    OrderState.ERROR:     [],
}


@dataclass
class OrderRecord:
    order_id:    str
    symbol:      str
    direction:   str
    lot:         float
    entry_price: float
    sl_price:    float
    tp_price:    float
    state:       OrderState      = OrderState.PENDING
    fill_price:  Optional[float] = None
    close_price: Optional[float] = None
    pnl:         float           = 0.0
    error_msg:   str             = ""
    created_at:  float           = field(default_factory=time.time)
    updated_at:  float           = field(default_factory=time.time)
    mt5_ticket:  Optional[int]   = None


StateChangeCallback = Callable[[str, OrderState, OrderState], None]


class OrderStateMachine:
    """Thread-safe singleton for order state management."""

    _instance: Optional["OrderStateMachine"] = None
    _cls_lock  = threading.Lock()

    @classmethod
    def get_instance(cls) -> "OrderStateMachine":
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._orders:    Dict[str, OrderRecord]    = {}
        self._callbacks: List[StateChangeCallback] = []
        self._lock       = threading.RLock()
        self._log        = logging.getLogger(self.__class__.__name__)

    def register(self, order: OrderRecord) -> None:
        with self._lock:
            if order.order_id in self._orders:
                raise ValueError(f"Already registered: {order.order_id}")
            self._orders[order.order_id] = order
            self._log.info("REGISTERED %s %s %s %.2f", order.order_id, order.symbol, order.direction, order.lot)

    def transition(
        self, order_id: str, new_state: OrderState, *,
        fill_price: Optional[float] = None, close_price: Optional[float] = None,
        pnl: Optional[float] = None, error_msg: str = "", mt5_ticket: Optional[int] = None,
    ) -> OrderRecord:
        with self._lock:
            o = self._get(order_id)
            old = o.state
            if new_state not in _ALLOWED.get(old, []):
                raise ValueError(f"Invalid: {old} -> {new_state} for {order_id}")
            o.state      = new_state
            o.updated_at = time.time()
            if fill_price  is not None: o.fill_price  = fill_price
            if close_price is not None: o.close_price = close_price
            if pnl         is not None: o.pnl         = pnl
            if error_msg:               o.error_msg   = error_msg
            if mt5_ticket  is not None: o.mt5_ticket  = mt5_ticket
            self._log.info("%s | %s->%s | pnl=%.2f", order_id, old.value, new_state.value, o.pnl)
            self._notify(order_id, old, new_state)
            return o

    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        with self._lock:
            return self._orders.get(order_id)

    def get_open_orders(self) -> List[OrderRecord]:
        with self._lock:
            open_s = {OrderState.SUBMITTED, OrderState.FILLED, OrderState.PARTIALLY_CLOSED}
            return [o for o in self._orders.values() if o.state in open_s]

    def cancel(self, order_id: str, reason: str = "") -> OrderRecord:
        return self.transition(order_id, OrderState.CANCELLED, error_msg=reason)

    def mark_error(self, order_id: str, msg: str) -> OrderRecord:
        return self.transition(order_id, OrderState.ERROR, error_msg=msg)

    def clear_closed(self) -> int:
        with self._lock:
            finals = {OrderState.CLOSED, OrderState.CANCELLED, OrderState.ERROR}
            keys   = [k for k, o in self._orders.items() if o.state in finals]
            for k in keys:
                del self._orders[k]
            return len(keys)

    def add_callback(self, cb: StateChangeCallback) -> None:
        with self._lock:
            self._callbacks.append(cb)

    def _get(self, order_id: str) -> OrderRecord:
        o = self._orders.get(order_id)
        if o is None:
            raise KeyError(f"Not found: {order_id}")
        return o

    def _notify(self, oid: str, old: OrderState, new: OrderState) -> None:
        for cb in self._callbacks:
            try:
                cb(oid, old, new)
            except Exception as exc:
                self._log.error("Callback error: %s", exc)
